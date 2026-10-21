"""
app/agents/interview_coach_agent.py
─────────────────────────────────────
Interview Coach Agent — LLM provider-agnostic.

Three prompt templates:
  1. generate_questions  — creates N interview questions for the session
  2. evaluate_answer     — deep narrative feedback on a single answer
  3. generate_report     — final session performance report

All numeric scores come from the rule-based evaluator (stable, never changes).
The LLM only generates narrative: feedback text, model answers, improvement tips.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.agents.interview_evaluator import EvaluationResult, evaluate_answer
from app.agents.interview_question_bank import (
    COMPANY_PROFILES,
    get_company_profile,
    get_hr_questions_for_prompt,
    get_technical_questions_for_prompt,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.llm_provider import call_llm, parse_llm_json

logger = get_logger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class GeneratedQuestion:
    question_text:  str
    question_type:  str   # hr | technical | behavioural | system_design | coding | culture_fit
    difficulty:     str
    follow_up_hint: str
    topic:          str   # for routing evaluator keyword pools


@dataclass
class AnswerFeedback:
    scores:          EvaluationResult
    qualitative:     dict           # from LLM: strengths, weaknesses, suggestions
    model_answer:    str
    improved_answer: str
    tokens_consumed: int = 0
    latency_ms:      int = 0


@dataclass
class SessionReport:
    overall_score:        float
    technical_score:      float
    confidence_score:     float
    communication_score:  float
    relevance_score:      float
    completeness_score:   float
    grade:                str
    verdict:              str
    executive_summary:    str
    strengths:            list[str]
    weaknesses:           list[str]
    improvement_tips:     list[dict]
    per_question_summary: list[dict]
    tokens_consumed:      int = 0
    processing_time_ms:   int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT 1 — Question Generation
# ═══════════════════════════════════════════════════════════════════════════════

def _build_question_prompt(
    mode:           str,
    target_role:    str | None,
    target_company: str | None,
    difficulty:     str,
    n:              int,
    resume_snippet: str,
    asked_so_far:   list[str],
) -> str:
    company_ctx = ""
    if target_company:
        profile = get_company_profile(target_company)
        if profile:
            company_ctx = f"""
COMPANY CONTEXT — {profile.name}:
Interview style: {profile.interview_style}
Rounds: {', '.join(profile.rounds)}
Core values: {', '.join(profile.values)}
Hot topics: {', '.join(profile.hot_topics)}
Sample questions from this company:
{chr(10).join(f'  • {q}' for q in profile.known_questions[:4])}
Tips: {', '.join(profile.tips)}
"""

    mode_instructions = {
        "hr": f"""Generate {n} HR interview questions.
Mix: 30% introduction/motivation, 30% STAR behavioural, 20% strengths/weaknesses, 20% company-fit.
Sample HR questions for inspiration (do NOT copy verbatim):
{get_hr_questions_for_prompt(6)}""",

        "technical": f"""Generate {n} technical interview questions for a {target_role or 'software engineer'} role.
Mix: 30% data structures/algorithms, 25% system design, 25% core CS concepts, 20% role-specific tech.
Sample technical questions for inspiration:
{get_technical_questions_for_prompt(n=5)}""",

        "company_specific": f"""Generate {n} interview questions SPECIFICALLY tailored to {target_company or 'this company'}.
Mirror their actual interview style, values, and known question patterns.
Mix: 40% technical/role-specific, 35% company-values behavioural, 25% product/business thinking.""",
    }

    already = "\n".join(f"- {q}" for q in asked_so_far) if asked_so_far else "None yet"

    return f"""You are an expert technical interviewer at a top tech company.

MODE: {mode.upper()} INTERVIEW
TARGET ROLE: {target_role or 'Software Engineer'}
DIFFICULTY: {difficulty.upper()}
{company_ctx}
CANDIDATE RESUME SNIPPET:
---
{resume_snippet[:800] if resume_snippet else 'Not provided'}
---
QUESTIONS ALREADY ASKED (do NOT repeat these):
{already}

TASK:
{mode_instructions.get(mode, mode_instructions['hr'])}

Return a JSON array of exactly {n} question objects:
[
  {{
    "question_text": "full question text — specific, not generic",
    "question_type": "hr | technical | behavioural | system_design | coding | situational | culture_fit",
    "difficulty": "easy | medium | hard",
    "follow_up_hint": "what a strong follow-up from the interviewer would probe",
    "topic": "e.g. system_design | data_structures | behavioural | motivation | python | java | databases"
  }}
]

RULES:
1. Questions must be specific to the role, not generic.
2. Harder difficulty → more open-ended and multi-part.
3. For company_specific mode, embed company values in behavioural questions.
4. Never repeat questions from the ALREADY ASKED list.
5. Follow-up hints should probe for depth (metrics, trade-offs, or edge cases).
6. Return ONLY the JSON array — no explanation outside it.
7. ANTI-HALLUCINATION: If a CANDIDATE RESUME SNIPPET is provided, only reference specific
   technologies/projects from it if they are literally present in the snippet. Do not assume
   the candidate has experience with a technology just because it's common for the target role.
   If no resume snippet is provided, ask role-general questions instead of guessing their background."""


def generate_questions(
    mode:           str,
    n:              int,
    target_role:    str | None,
    target_company: str | None,
    difficulty:     str,
    resume_text:    str = "",
    asked_so_far:   list[str] = None,
) -> list[GeneratedQuestion]:
    """Generate N interview questions via the centralised LLM provider."""
    t0     = time.monotonic()
    prompt = _build_question_prompt(
        mode, target_role, target_company, difficulty, n,
        resume_text, asked_so_far or []
    )

    try:
        raw, tokens = call_llm(prompt, temperature=0.4, max_tokens=1500, json_mode=False)
    except RuntimeError:
        logger.warning("llm_provider_unavailable_using_fallback_questions")
        return _fallback_questions(mode, n, target_role, difficulty)

    parsed = parse_llm_json(raw)

    questions: list[GeneratedQuestion] = []
    if isinstance(parsed, list):
        for item in parsed[:n]:
            if isinstance(item, dict) and "question_text" in item:
                questions.append(GeneratedQuestion(
                    question_text=item.get("question_text", ""),
                    question_type=item.get("question_type", "hr"),
                    difficulty=item.get("difficulty", difficulty),
                    follow_up_hint=item.get("follow_up_hint", ""),
                    topic=item.get("topic", "general"),
                ))

    if not questions:
        questions = _fallback_questions(mode, n, target_role, difficulty)

    logger.info("questions_generated", mode=mode, n=len(questions),
                ms=int((time.monotonic() - t0) * 1000),
                provider=settings.DEFAULT_LLM_PROVIDER)
    return questions[:n]


def _fallback_questions(mode: str, n: int, role: str | None, difficulty: str) -> list[GeneratedQuestion]:
    """Static fallback when LLM is unavailable."""
    role_label = role or "this role"
    pools = {
        "hr": [
            GeneratedQuestion("Tell me about yourself and your journey to this field.", "hr", difficulty, "Probe specific career decisions.", "introduction"),
            GeneratedQuestion(f"Why are you interested in the {role_label} position?", "culture_fit", difficulty, "Ask what research they did on the company.", "motivation"),
            GeneratedQuestion("Describe a challenging project and how you overcame it.", "behavioural", difficulty, "Ask for metrics on the outcome.", "star"),
            GeneratedQuestion("What is your greatest professional weakness?", "hr", difficulty, "Ask what they are actively doing to improve.", "strengths_weaknesses"),
            GeneratedQuestion("Where do you see yourself in five years?", "hr", difficulty, "Ask how this role fits into that vision.", "motivation"),
        ],
        "technical": [
            GeneratedQuestion(f"Explain the most complex technical problem you have solved as a {role_label}.", "technical", difficulty, "Ask about trade-offs considered.", "general_technical"),
            GeneratedQuestion("Design a notification system that handles 1 million users.", "system_design", difficulty, "Ask about failure scenarios.", "system_design"),
            GeneratedQuestion("What is the difference between SQL and NoSQL databases?", "technical", difficulty, "Ask when they would choose one over the other.", "databases"),
            GeneratedQuestion("Explain how you would optimise a slow database query.", "technical", difficulty, "Ask about indexing strategies.", "databases"),
            GeneratedQuestion("What design patterns have you used in production code?", "technical", difficulty, "Ask for a concrete example.", "general_technical"),
        ],
        "company_specific": [
            GeneratedQuestion("What do you know about our company and why do you want to join us specifically?", "culture_fit", difficulty, "Probe for depth of research.", "company_fit"),
            GeneratedQuestion(f"How would you approach a disagreement with your tech lead at {role or 'our company'}?", "behavioural", difficulty, "Ask what they learned.", "star"),
            GeneratedQuestion("Design a scalable feature for our core product.", "system_design", difficulty, "Ask about monitoring strategy.", "system_design"),
            GeneratedQuestion("Tell me about a time you delivered results under a tight deadline.", "behavioural", difficulty, "Ask for quantified outcome.", "star"),
            GeneratedQuestion("How do you stay updated with new technologies in our domain?", "hr", difficulty, "Ask for a recent thing they learned.", "motivation"),
        ],
    }
    pool = pools.get(mode, pools["hr"])
    return (pool * ((n // len(pool)) + 1))[:n]


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT 2 — Answer Evaluation
# ═══════════════════════════════════════════════════════════════════════════════

def _build_evaluation_prompt(
    question:      str,
    answer:        str,
    question_type: str,
    scores:        EvaluationResult,
    target_role:   str | None,
) -> str:
    return f"""You are a strict but constructive interview coach evaluating a candidate's answer.

QUESTION: {question}
QUESTION TYPE: {question_type}
TARGET ROLE: {target_role or 'Software Engineer'}

CANDIDATE'S ANSWER:
---
{answer}
---

PRE-COMPUTED SCORES (treat as ground truth — do NOT contradict these numbers):
- Confidence Score:     {scores.confidence_score}/100
- Technical Score:      {scores.technical_score}/100
- Communication Score:  {scores.communication_score}/100
- Relevance Score:      {scores.relevance_score}/100
- Completeness Score:   {scores.completeness_score}/100
- Overall Score:        {scores.overall_score}/100
- Word Count:           {scores.word_count}
- Has Quantified Metrics: {scores.has_metrics}
- STAR Components Found: {json.dumps(scores.star_breakdown)}

Return a single JSON object:
{{
  "strengths": [
    "specific strength from THIS answer with evidence — not generic"
  ],
  "weaknesses": [
    "specific weakness or gap in THIS answer"
  ],
  "improvement_suggestions": [
    {{
      "issue": "what specifically was weak",
      "fix":   "exactly how to improve it, with an example phrase",
      "impact": "high | medium | low"
    }}
  ],
  "model_answer": "A strong 150-200 word model answer for this exact question, appropriate for {target_role or 'a software engineering role'}.",
  "improved_version": "Take the candidate's answer and rewrite it better — fix structure, add specifics, use STAR if behavioural. Keep their core content but elevate it.",
  "interviewer_impression": "1 sentence on what an interviewer would think hearing this answer",
  "score_justification": "2-3 sentences explaining the scores objectively"
}}

RULES:
1. Be specific — cite actual phrases from their answer.
2. Model answer must be role-appropriate and use STAR if behavioural.
3. Improved version should feel like the same person, but polished.
4. Improvement suggestions: max 3, sorted by impact descending.
5. Return ONLY the JSON object.
6. ANTI-HALLUCINATION — CRITICAL: When writing "improved_version", you MUST preserve every
   specific technology, tool, company name, project name, and metric the candidate actually
   mentioned in their answer. NEVER swap their named technology for a different one (e.g. if
   they said "I used Flask", do not rewrite it as "I used FastAPI" — improve clarity and
   structure only, not their factual claims).
7. The "model_answer" is a separate, hypothetical ideal answer for the question — it may use
   different example technologies since it's not claiming to be the candidate's real experience.
   But "improved_version" is a rewrite of THEIR answer and must stay 100% faithful to what they
   actually said, only fixing structure, clarity, and missing detail they could plausibly add.
8. Do not invent metrics or outcomes the candidate did not state. If their answer lacks a metric,
   note that as a weakness — do not silently insert a fabricated number into improved_version."""


def evaluate_answer_with_ai(
    question:      str,
    answer:        str,
    question_type: str,
    target_role:   str | None,
    topic:         str | None = None,
) -> AnswerFeedback:
    """Full answer evaluation: rule-based scores + LLM narrative."""
    t0     = time.monotonic()
    scores = evaluate_answer(question, answer, question_type, target_role, topic)

    prompt = _build_evaluation_prompt(question, answer, question_type, scores, target_role)
    try:
        raw, tokens = call_llm(prompt, temperature=0.4, max_tokens=1500, json_mode=True)
        qualitative = parse_llm_json(raw)
    except RuntimeError:
        logger.warning("llm_provider_unavailable_answer_evaluation_mock")
        qualitative, tokens = {}, 0

    if not isinstance(qualitative, dict):
        qualitative = {}

    model_answer = qualitative.pop("model_answer", _generic_model_answer(question, question_type))
    improved     = qualitative.pop("improved_version", answer)

    return AnswerFeedback(
        scores=scores,
        qualitative=qualitative,
        model_answer=model_answer,
        improved_answer=improved,
        tokens_consumed=tokens,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


def _generic_model_answer(question: str, qtype: str) -> str:
    if qtype in ("hr", "behavioural"):
        return (
            "A strong answer would follow the STAR method: describe the Situation clearly, "
            "explain your Task or role, walk through the specific Actions you took step by step, "
            "and quantify the Result (e.g., improved performance by 30%, reduced bugs by 40%). "
            "Configure a LLM provider for a personalised model answer."
        )
    return (
        "A strong technical answer defines the concept clearly, provides a concrete example, "
        "discusses trade-offs, and mentions time/space complexity where applicable. "
        "Configure a LLM provider for a personalised model answer."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT 3 — Final Session Report
# ═══════════════════════════════════════════════════════════════════════════════

def _build_report_prompt(
    mode:         str,
    target_role:  str | None,
    company:      str | None,
    questions:    list[dict],
    avg_scores:   dict,
) -> str:
    q_summary = "\n".join(
        f"Q{i+1} [{q['type']}] (score: {q['score']:.0f}/100): {q['question'][:80]}..."
        if len(q['question']) > 80 else
        f"Q{i+1} [{q['type']}] (score: {q['score']:.0f}/100): {q['question']}"
        for i, q in enumerate(questions)
    )
    return f"""You are a senior technical interviewer writing a post-interview performance report.

SESSION SUMMARY:
Mode: {mode.upper()} | Role: {target_role or 'Software Engineer'} | Company: {company or 'General'}
Questions Attempted: {len(questions)}

AVERAGE SCORES:
- Overall:       {avg_scores['overall']:.1f}/100
- Technical:     {avg_scores['technical']:.1f}/100
- Confidence:    {avg_scores['confidence']:.1f}/100
- Communication: {avg_scores['communication']:.1f}/100
- Relevance:     {avg_scores['relevance']:.1f}/100
- Completeness:  {avg_scores['completeness']:.1f}/100

QUESTION BREAKDOWN:
{q_summary}

Write a post-interview coaching report. Return a single JSON object:
{{
  "executive_summary": "3-4 sentence honest assessment of overall interview performance. Be specific about what worked and what didn't.",
  "strengths": [
    "Specific observable strength across the session with evidence"
  ],
  "weaknesses": [
    "Specific observable weakness with evidence from the session"
  ],
  "improvement_tips": [
    {{
      "area":     "e.g. STAR Method | Technical Depth | Confidence",
      "current":  "what they are doing now",
      "target":   "what good looks like",
      "action":   "specific practice exercise to improve",
      "timeline": "e.g. 1 week of daily practice"
    }}
  ],
  "per_question_summary": [
    {{
      "question_number": 1,
      "score": 72,
      "highlight": "one-sentence note on the best or worst aspect of this answer"
    }}
  ],
  "readiness_verdict": "Ready to interview | Needs 2-4 weeks practice | Needs significant preparation",
  "next_steps": ["specific action 1", "specific action 2", "specific action 3"]
}}

RULES:
1. Be honest — if scores are low, say so constructively.
2. Strengths/weaknesses: max 3 each, backed by evidence.
3. improvement_tips: max 4, sorted by impact.
4. Return ONLY the JSON object.
5. ANTI-HALLUCINATION: The AVERAGE SCORES and QUESTION BREAKDOWN above are computed
   deterministically — treat them as ground truth and never contradict these numbers in your
   narrative. Every strength/weakness you list must be traceable to the actual question scores
   shown above (e.g. do not call communication a "strength" if the communication score is below 60)."""


def generate_session_report(
    mode:         str,
    target_role:  str | None,
    company:      str | None,
    questions:    list[dict],
    avg_scores:   dict,
) -> SessionReport:
    """Generate the final interview performance report."""
    t0     = time.monotonic()
    prompt = _build_report_prompt(mode, target_role, company, questions, avg_scores)

    try:
        raw, tokens = call_llm(prompt, temperature=0.3, max_tokens=2000, json_mode=True)
        data = parse_llm_json(raw)
    except RuntimeError:
        logger.warning("llm_provider_unavailable_session_report_mock")
        data, tokens = {}, 0

    if not isinstance(data, dict):
        data = {}

    overall = avg_scores["overall"]
    grade   = _score_to_grade(overall)
    verdict = data.get("readiness_verdict", _default_verdict(overall))

    return SessionReport(
        overall_score=overall,
        technical_score=avg_scores["technical"],
        confidence_score=avg_scores["confidence"],
        communication_score=avg_scores["communication"],
        relevance_score=avg_scores["relevance"],
        completeness_score=avg_scores["completeness"],
        grade=grade,
        verdict=verdict,
        executive_summary=data.get("executive_summary", "Configure LLM provider for AI report."),
        strengths=data.get("strengths", []),
        weaknesses=data.get("weaknesses", []),
        improvement_tips=data.get("improvement_tips", []),
        per_question_summary=data.get("per_question_summary", [
            {"question_number": i+1, "score": q["score"], "highlight": ""}
            for i, q in enumerate(questions)
        ]),
        tokens_consumed=tokens,
        processing_time_ms=int((time.monotonic() - t0) * 1000),
    )


def _score_to_grade(score: float) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "F"


def _default_verdict(score: float) -> str:
    if score >= 80: return "Ready to interview"
    if score >= 60: return "Needs 2-4 weeks practice"
    return "Needs significant preparation"
