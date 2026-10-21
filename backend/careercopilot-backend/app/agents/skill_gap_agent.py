"""
app/agents/skill_gap_agent.py
──────────────────────────────
Skill Gap Analyzer Agent — LLM provider-agnostic.

Pipeline:
  1. Extract skills from resume text (rule-based NLP)
  2. Match against role skill DB (deterministic scorer)
  3. Build rich prompt with pre-computed scores
  4. Call centralised LLM provider (Groq by default)
  5. Parse structured JSON response
  6. Merge rule-based scores with LLM narrative
  7. Return SkillGapAnalysisResult

The LLM is responsible for:
  - Personalised executive summary
  - Prioritised learning roadmap with real course links
  - Project ideas to fill gaps
  - Salary insights and career strategy advice
  - Quick wins (achievable in < 2 weeks)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.agents.role_skill_db import Priority, get_role, ROLE_REGISTRY
from app.agents.skill_matcher import (
    SkillMatchResult,
    extract_skills_from_text,
    match_skills,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.llm_provider import call_llm, parse_llm_json

logger = get_logger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SkillGapAnalysisResult:
    # Identity
    role_key:              str
    role_title:            str
    target_company:        str | None = None

    # Scores (rule-based — always authoritative)
    overall_match_pct:     float = 0.0
    required_match_pct:    float = 0.0
    preferred_match_pct:   float = 0.0
    gap_severity:          str   = "major"
    estimated_prep_months: int   = 6

    # Skill breakdown (serialisable dicts)
    matched_skills:        list[dict] = field(default_factory=list)
    missing_required:      list[dict] = field(default_factory=list)
    missing_preferred:     list[dict] = field(default_factory=list)

    # LLM-generated content
    executive_summary:     str        = ""
    detailed_feedback:     str        = ""
    learning_priorities:   list[dict] = field(default_factory=list)
    recommended_courses:   list[dict] = field(default_factory=list)
    recommended_projects:  list[dict] = field(default_factory=list)
    recommended_certs:     list[dict] = field(default_factory=list)
    quick_wins:            list[dict] = field(default_factory=list)
    strengths:             list[str]  = field(default_factory=list)
    salary_insight:        str        = ""

    # Meta
    candidate_skills:      list[str]  = field(default_factory=list)
    model_used:            str        = ""
    tokens_consumed:       int        = 0
    processing_time_ms:    int        = 0


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    resume_text:    str,
    role_key:       str,
    match_result:   SkillMatchResult,
    target_company: str | None,
) -> str:
    role        = get_role(role_key)
    company_ctx = f"Target Company: {target_company}" if target_company else "Target Company: Not specified"

    matched_names  = [m.role_skill_name for m in match_result.matched]
    missing_req    = [
        {"name": s.name, "priority": s.priority.value, "description": s.description}
        for s in match_result.missing_required
    ]
    missing_pref   = [s.name for s in match_result.missing_preferred[:8]]
    critical_gaps  = [s.name for s in match_result.missing_required if s.priority == Priority.CRITICAL]
    high_gaps      = [s.name for s in match_result.missing_required if s.priority == Priority.HIGH]

    salary_low, salary_high = role.salary_range_inr
    certs_preview  = list(role.certifications[:4])

    return f"""You are a senior technical career coach and hiring manager with 15+ years of experience at top tech companies.

## TASK
Analyse the skill gap between this candidate and the target role, then produce a **single valid JSON object** — no markdown fences, no preamble.

## CANDIDATE ANALYSIS (already computed — use these numbers exactly)
- Target Role: {role.title}
- {company_ctx}
- Overall Match: {match_result.overall_match_pct}%
- Required Skills Match: {match_result.required_match_pct}%
- Preferred Skills Match: {match_result.preferred_match_pct}%
- Gap Severity: {match_result.gap_severity}
- Estimated Preparation Time: {match_result.estimated_prep_months} months

## MATCHED SKILLS (candidate already has these)
{json.dumps(matched_names, indent=2)}

## MISSING CRITICAL SKILLS (must fix immediately)
{json.dumps(critical_gaps)}

## MISSING HIGH-PRIORITY SKILLS
{json.dumps(high_gaps)}

## MISSING PREFERRED SKILLS
{json.dumps(missing_pref)}

## ROLE CONTEXT
{role.description}
Salary Range (India): ₹{salary_low}–{salary_high} LPA
Career Path: {" → ".join(role.career_path)}
Relevant Certifications: {json.dumps(certs_preview)}

## RESUME TEXT (first 3000 chars)
---
{resume_text[:3000]}
---

## OUTPUT JSON SCHEMA (all fields required)
{{
  "executive_summary": "3-4 sentence personalised summary: current standing, biggest gaps, realistic timeline, motivation.",
  "detailed_feedback": "2-3 paragraphs of honest, specific, actionable feedback on the candidate's profile vs the role.",
  "strengths": [
    "Specific strength observed in the resume with evidence — not generic"
  ],
  "learning_priorities": [
    {{
      "rank": 1,
      "skill": "exact skill name from missing list",
      "why": "why this is the #1 priority — impact on hiring decision",
      "time_weeks": 6,
      "approach": "exactly how to learn this (specific resources, project, method)"
    }}
  ],
  "recommended_courses": [
    {{
      "title": "exact course name",
      "platform": "Coursera | Udemy | YouTube | Official Docs | freeCodeCamp | fast.ai",
      "url": "real URL if known, else empty string",
      "skill_covered": "which missing skill this addresses",
      "duration_weeks": 4,
      "is_free": false,
      "priority": "high | medium | low"
    }}
  ],
  "recommended_projects": [
    {{
      "title": "specific project name",
      "description": "2-sentence project description that directly demonstrates missing skills",
      "skills_covered": ["skill1", "skill2"],
      "difficulty": "beginner | intermediate | advanced",
      "estimated_hours": 20
    }}
  ],
  "recommended_certs": [
    {{
      "name": "certification name",
      "issuer": "AWS | Google | Oracle | etc.",
      "why": "why this cert specifically boosts candidacy for this role",
      "estimated_months": 2,
      "cost_usd": 150
    }}
  ],
  "quick_wins": [
    {{
      "action": "specific action completable in under 2 weeks",
      "impact": "how this immediately improves the resume/profile",
      "time_days": 7
    }}
  ],
  "salary_insight": "Personalised salary insight: given their current match %, what range they can realistically target now vs after closing gaps."
}}

## RULES
1. learning_priorities: list ONLY missing skills, sorted by impact on getting hired. Max 8.
2. recommended_courses: 4-6 courses max. Choose well-known, high-quality resources. No made-up URLs.
3. recommended_projects: 3-4 projects that fill the biggest gaps AND are portfolio-worthy.
4. quick_wins: 3-5 things the candidate can do THIS WEEK.
5. Be SPECIFIC and HONEST — avoid generic advice like "learn Python more". Say EXACTLY what to build.
6. Strengths: cite EVIDENCE from the resume. Max 4 strengths.

## ANTI-HALLUCINATION RULES (CRITICAL)
7. The MATCHED SKILLS, MISSING CRITICAL SKILLS, MISSING HIGH-PRIORITY SKILLS, and MISSING
   PREFERRED SKILLS lists above are computed deterministically — they are ground truth.
   NEVER add a skill to "strengths" that is not in the MATCHED SKILLS list.
   NEVER claim the candidate is missing a skill that is not in one of the missing-skill lists.
8. NEVER invent a certification, project, or course that does not actually exist. Only recommend
   real, well-known platforms (Coursera, Udemy, freeCodeCamp, official docs, YouTube channels).
9. If the resume text does not mention something specific (e.g. years of experience with a tool),
   say "Not found in the provided resume" rather than guessing.
10. Strengths must cite evidence directly from the RESUME TEXT block — not from assumptions
    about what someone with these skills "probably" knows."""


# ── Serialisers ───────────────────────────────────────────────────────────────

def _serialise_matched(match_result: SkillMatchResult) -> list[dict]:
    return [
        {
            "name":           m.role_skill_name,
            "candidate_name": m.candidate_skill,
            "priority":       m.priority.value,
            "category":       m.category,
            "match_type":     m.match_type,
        }
        for m in match_result.matched
    ]


def _serialise_missing(skills) -> list[dict]:
    return [
        {
            "name":            s.name,
            "priority":        s.priority.value,
            "category":        s.category,
            "min_proficiency": s.min_proficiency.value,
            "description":     s.description,
            "learning_url":    s.learning_url,
        }
        for s in skills
    ]


# ── Main agent entrypoint ─────────────────────────────────────────────────────

def run_skill_gap_analysis(
    resume_text:    str,
    role_key:       str,
    target_company: str | None  = None,
    extra_skills:   list[str]   = None,
) -> SkillGapAnalysisResult:
    """
    Full Skill Gap Analysis pipeline:
      1. Extract skills from resume text
      2. Merge with any manually provided skills
      3. Match against role DB (deterministic)
      4. Enrich with LLM narrative via centralised provider
      5. Return merged result
    """
    t0 = time.monotonic()

    # 1. Extract + merge skills
    nlp_skills = extract_skills_from_text(resume_text)
    all_skills = list({*nlp_skills, *(extra_skills or [])})
    logger.info("skill_gap_extraction", role=role_key, skills_found=len(all_skills))

    # 2. Deterministic match
    match_result = match_skills(all_skills, role_key)

    # 3. LLM enrichment
    prompt = _build_prompt(resume_text, role_key, match_result, target_company)
    try:
        raw, tokens = call_llm(prompt, temperature=0.2, max_tokens=4096, json_mode=True)
    except RuntimeError:
        logger.warning("llm_provider_unavailable_skill_gap_mock")
        raw, tokens = json.dumps({
            "executive_summary": "Configure LLM provider API key for AI analysis.",
            "detailed_feedback": "Set GROQ_API_KEY in .env to enable analysis.",
            "strengths": [], "learning_priorities": [], "recommended_courses": [],
            "recommended_projects": [], "recommended_certs": [],
            "quick_wins": [{"action": "Set GROQ_API_KEY in .env", "impact": "Enables AI analysis", "time_days": 1}],
            "salary_insight": "Configure LLM provider for salary insights.",
        }), 0

    llm_data = parse_llm_json(raw)
    if not isinstance(llm_data, dict):
        llm_data = {}

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("skill_gap_complete", role=role_key,
                match=match_result.overall_match_pct, ms=elapsed_ms,
                provider=settings.DEFAULT_LLM_PROVIDER)

    return SkillGapAnalysisResult(
        role_key=role_key,
        role_title=match_result.role_title,
        target_company=target_company,

        # Rule-based scores (always authoritative)
        overall_match_pct=match_result.overall_match_pct,
        required_match_pct=match_result.required_match_pct,
        preferred_match_pct=match_result.preferred_match_pct,
        gap_severity=match_result.gap_severity,
        estimated_prep_months=match_result.estimated_prep_months,

        # Skill lists
        matched_skills=_serialise_matched(match_result),
        missing_required=_serialise_missing(match_result.missing_required),
        missing_preferred=_serialise_missing(match_result.missing_preferred),

        # LLM narrative (empty fallback if provider unavailable)
        executive_summary=llm_data.get("executive_summary", ""),
        detailed_feedback=llm_data.get("detailed_feedback", ""),
        strengths=llm_data.get("strengths", []),
        learning_priorities=llm_data.get("learning_priorities", []),
        recommended_courses=llm_data.get("recommended_courses", []),
        recommended_projects=llm_data.get("recommended_projects", []),
        recommended_certs=llm_data.get("recommended_certs", []),
        quick_wins=llm_data.get("quick_wins", []),
        salary_insight=llm_data.get("salary_insight", ""),

        candidate_skills=all_skills,
        model_used=settings.active_model,
        tokens_consumed=tokens,
        processing_time_ms=elapsed_ms,
    )
