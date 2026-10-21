"""
app/agents/resume_agent.py
──────────────────────────
Resume Analyser Agent — LLM provider-agnostic.

Responsibilities:
  1. Receive pre-extracted text + NLP entities + ATS scores
  2. Build a structured prompt requesting JSON output
  3. Call the centralised LLM provider (Groq by default)
  4. Parse and validate the LLM response
  5. Merge LLM insights with rule-based ATS scores
  6. Return a fully populated ResumeAnalysisResult dataclass

The LLM is used for:
  - Deeper skill/project/experience extraction with context
  - Natural language summary generation
  - Actionable, specific improvement suggestions
  - Soft-skill and leadership inference
  - Cover-letter readiness assessment
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.llm_provider import call_llm, parse_llm_json
from app.utils.ats_scorer import ATSScoreResult
from app.utils.nlp_extractor import ExtractedEntities

logger = get_logger(__name__)


# ── Result dataclass returned by the agent ────────────────────────────────────

@dataclass
class ResumeAnalysisResult:
    # Scores (from ATS scorer, confirmed/adjusted by LLM)
    ats_score:          float = 0.0
    formatting_score:   float = 0.0
    content_score:      float = 0.0
    keyword_score:      float = 0.0
    experience_score:   float = 0.0
    grade:              str   = "F"
    verdict:            str   = ""

    # LLM-enriched extractions
    skills:             list[dict] = field(default_factory=list)
    projects:           list[dict] = field(default_factory=list)
    certifications:     list[dict] = field(default_factory=list)
    education:          list[dict] = field(default_factory=list)
    experience:         list[dict] = field(default_factory=list)
    contact_info:       dict       = field(default_factory=dict)

    # Analysis narrative
    summary:            str        = ""
    strengths:          list[str]  = field(default_factory=list)
    improvements:       list[dict] = field(default_factory=list)
    keywords_found:     list[str]  = field(default_factory=list)
    keywords_missing:   list[str]  = field(default_factory=list)
    seniority_match:    str        = "undetected"
    seniority_detected: str | None = None

    # Meta
    total_years_experience: float = 0.0
    model_used:         str       = ""
    tokens_consumed:    int       = 0
    processing_time_ms: int       = 0


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_analysis_prompt(
    resume_text: str,
    entities:    ExtractedEntities,
    ats_result:  ATSScoreResult,
    target_role: str | None,
) -> str:
    """
    Construct the master analysis prompt.
    We provide pre-extracted data so the LLM focuses on reasoning and enrichment,
    not raw parsing — this reduces hallucinations and token usage.
    """
    skills_preview = ", ".join(entities.technical_skills[:20]) or "none detected"
    certs_preview  = ", ".join(c["name"] for c in entities.certifications[:5]) or "none detected"
    yoe            = entities.total_years_exp
    target_context = f"Target Role: {target_role}" if target_role else "Target Role: not specified"

    return f"""You are an expert resume analyst and career coach with 15+ years of experience reviewing resumes for top tech companies including Google, Amazon, Microsoft, and leading startups.

## TASK
Analyse the resume text below and return a **single valid JSON object** — no markdown fences, no preamble, no explanation outside the JSON.

## PRE-ANALYSIS CONTEXT (from automated parsing)
- Skills detected: {skills_preview}
- Certifications detected: {certs_preview}
- Years of experience (computed from dates): {yoe}
- ATS score (rule-based): {ats_result.ats_score}/100
- {target_context}

## RESUME TEXT
---
{resume_text[:6000]}
---

## OUTPUT SCHEMA
Return exactly this JSON structure (all fields required, use null if unknown):

{{
  "contact_info": {{
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "github": "string or null",
    "website": "string or null"
  }},
  "skills": [
    {{
      "name": "skill name",
      "category": "language|framework|database|cloud|devops|tool|concept|soft",
      "proficiency": "beginner|intermediate|advanced|expert",
      "years": null
    }}
  ],
  "projects": [
    {{
      "title": "project name",
      "description": "1-2 sentence description",
      "technologies": ["tech1", "tech2"],
      "impact": "quantified result or null",
      "url": "url or null"
    }}
  ],
  "certifications": [
    {{
      "name": "cert name",
      "issuer": "issuer or null",
      "year": 2023,
      "expiry_year": null,
      "credential_id": null
    }}
  ],
  "education": [
    {{
      "degree": "B.Tech / M.Tech / PhD etc or null",
      "institution": "university name or null",
      "field": "Computer Science etc or null",
      "year": 2020,
      "gpa": "8.5/10 or null"
    }}
  ],
  "experience": [
    {{
      "title": "job title",
      "company": "company name or null",
      "start_date": "Jan 2022 or null",
      "end_date": "Dec 2023 or null",
      "is_current": false,
      "description": "role summary",
      "achievements": ["achievement 1 with metric", "achievement 2"],
      "technologies": ["tech1", "tech2"]
    }}
  ],
  "summary": "3-4 sentence professional summary of this candidate's profile, strengths, and readiness",
  "strengths": [
    "Specific strength 1 — be concrete, not generic",
    "Specific strength 2",
    "Specific strength 3"
  ],
  "improvements": [
    {{
      "category": "formatting|content|keywords|experience|education",
      "issue": "Specific problem found in the resume",
      "suggestion": "Concrete, actionable fix with example",
      "priority": "high|medium|low"
    }}
  ],
  "keywords_found": ["keyword1", "keyword2"],
  "keywords_missing": ["keyword1", "keyword2"],
  "seniority_detected": "Junior / Entry-Level | Mid-Level | Senior | Principal / Director",
  "total_years_experience": {yoe}
}}

## ANALYSIS RULES
1. Extract ALL skills mentioned — both explicit (skills section) and implicit (used in project/experience descriptions)
2. For improvements: be SPECIFIC. Bad: "Add more details". Good: "Your 'Built microservice' bullet lacks impact — add user count, latency improvement, or cost savings"
3. For strengths: cite EVIDENCE from the resume, don't just say "strong technical background"
4. keywords_missing should be role-relevant keywords absent from the resume (suggest 5-8 realistic gaps)
5. If a section is missing entirely (e.g. no projects), flag it as a HIGH priority improvement
6. Validate and correct the contact info if you see it in the resume text
7. Total years experience should be calculated from actual employment dates, not assumed

## ANTI-HALLUCINATION RULES (CRITICAL — violating these makes your output unusable)
8. NEVER invent a skill, certification, project, employer, degree, or achievement that is not
   literally present in the RESUME TEXT above. If you are not at least 90% certain something
   is stated in the text, omit it.
9. If a field genuinely cannot be determined from the resume text (e.g. no LinkedIn URL found,
   no GPA mentioned), set that field to null — do NOT guess or fabricate a plausible-looking value.
10. For "strengths" and "improvements": every claim must trace back to specific text in the
    resume. If you cannot point to the sentence that supports a strength, do not list it.
11. Do not assume technologies were used together just because they appear in the same resume —
    only group them if the resume text explicitly says so (e.g. "built with X and Y").
12. If the resume text is too short or garbled to confidently extract a section, return an empty
    array for that section rather than inventing plausible-sounding content."""


# ── Mock response for dev mode ────────────────────────────────────────────────

def _mock_response() -> str:
    import json
    return json.dumps({
        "contact_info": {
            "name": "Candidate Name", "email": "candidate@example.com",
            "phone": None, "location": None, "linkedin": None,
            "github": None, "website": None,
        },
        "skills": [{"name": "Python", "category": "language", "proficiency": "advanced", "years": 3}],
        "projects": [], "certifications": [], "education": [], "experience": [],
        "summary": "Configure LLM provider API key for real AI-powered analysis.",
        "strengths": ["Set GROQ_API_KEY in .env to enable AI analysis"],
        "improvements": [{
            "category": "content", "issue": "LLM provider not configured",
            "suggestion": "Set GROQ_API_KEY (or GEMINI_API_KEY) in .env",
            "priority": "high",
        }],
        "keywords_found": [], "keywords_missing": [],
        "seniority_detected": "Mid-Level", "total_years_experience": 0.0,
    })


# ── Main agent entrypoint ─────────────────────────────────────────────────────

def run_resume_analysis(
    resume_text:  str,
    entities:     ExtractedEntities,
    ats_result:   ATSScoreResult,
    page_count:   int,
    word_count:   int,
    target_role:  str | None = None,
) -> ResumeAnalysisResult:
    """
    Orchestrate the full analysis pipeline:
      NLP entities + ATS scores → LLM enrichment → merged result
    """
    t0 = time.monotonic()

    prompt = _build_analysis_prompt(resume_text, entities, ats_result, target_role)

    try:
        raw, tokens = call_llm(
            prompt,
            temperature=0.1,   # low temp for factual extraction
            max_tokens=4096,
            json_mode=True,
        )
    except RuntimeError:
        # LLM provider not configured — use mock in dev
        logger.warning("llm_provider_unavailable_using_mock")
        raw, tokens = _mock_response(), 0

    llm_data: dict[str, Any] = parse_llm_json(raw)  # type: ignore[assignment]
    if not isinstance(llm_data, dict):
        llm_data = {}

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("resume_analysis_complete", tokens=tokens, ms=elapsed_ms,
                provider=settings.DEFAULT_LLM_PROVIDER)

    return ResumeAnalysisResult(
        # ATS scores are rule-based — always authoritative
        ats_score          = ats_result.ats_score,
        formatting_score   = ats_result.formatting_score,
        content_score      = ats_result.content_score,
        keyword_score      = ats_result.keyword_score,
        experience_score   = ats_result.experience_score,
        grade              = ats_result.grade,
        verdict            = ats_result.verdict,

        # LLM-enriched fields (fall back to NLP entities if LLM fails)
        skills             = llm_data.get("skills",           entities.skills),
        projects           = llm_data.get("projects",         []),
        certifications     = llm_data.get("certifications",   entities.certifications),
        education          = llm_data.get("education",        entities.education_items),
        experience         = llm_data.get("experience",       []),
        contact_info       = llm_data.get("contact_info",     entities.contact),

        summary            = llm_data.get("summary",          ""),
        strengths          = llm_data.get("strengths",        ats_result.strengths),
        improvements       = llm_data.get("improvements",     []),
        keywords_found     = llm_data.get("keywords_found",   ats_result.keywords_found),
        keywords_missing   = llm_data.get("keywords_missing", ats_result.keywords_missing),
        seniority_match    = ats_result.seniority_match,
        seniority_detected = llm_data.get("seniority_detected", entities.detected_seniority),

        total_years_experience = float(llm_data.get("total_years_experience", entities.total_years_exp)),
        model_used         = settings.active_model,
        tokens_consumed    = tokens,
        processing_time_ms = elapsed_ms,
    )
