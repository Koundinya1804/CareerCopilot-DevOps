"""
app/agents/career_recommendation_agent.py
──────────────────────────────────────────
Career Recommendation Agent — LLM provider-agnostic.

Workflow:
  1. Extract skills + profile from resume text (NLP)
  2. Score all 20 career roles (multi-signal algorithm)
  3. Build structured prompt with pre-computed scores
  4. Call centralised LLM provider (Groq by default)
  5. Merge and return unified CareerRecommendationOutput
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.agents.career_role_catalogue import ROLES
from app.agents.recommendation_engine import (
    RecommendationResult,
    RoleScore,
    score_all_roles,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.llm_provider import call_llm, parse_llm_json

logger = get_logger(__name__)


# ── Output dataclasses ────────────────────────────────────────────────────────

@dataclass
class RecommendedRoleDetail:
    rank:               int
    role_key:           str
    role_title:         str
    role_icon:          str
    domain:             str
    suitability_score:  float
    suitability_label:  str
    confidence:         str
    skill_match_pct:    float
    interest_match_pct: float

    # LLM-generated per-role content
    why_suited:          str       = ""
    what_youll_do:       str       = ""
    skill_gaps:          list[str] = field(default_factory=list)
    salary_journey:      dict      = field(default_factory=dict)
    top_companies:       list[str] = field(default_factory=list)
    related_roles:       list[str] = field(default_factory=list)
    transition_timeline: str       = ""


@dataclass
class CareerRecommendationOutput:
    # Top recommendations
    recommended_roles:   list[RecommendedRoleDetail]
    # Full score table (all 20 roles)
    all_role_scores:     list[dict]
    # Domain fit
    domain_fit:          dict
    best_domain:         str

    # LLM narrative
    career_narrative:    str  = ""
    personality_profile: dict = field(default_factory=dict)
    market_trends:       dict = field(default_factory=dict)
    action_plan:         dict = field(default_factory=dict)
    industry_insights:   str  = ""

    # Input echo
    candidate_skills:    list[str] = field(default_factory=list)
    candidate_interests: list[str] = field(default_factory=list)
    years_experience:    float = 0.0
    education_level:     str   = ""

    # Meta
    model_used:          str = ""
    tokens_consumed:     int = 0
    processing_time_ms:  int = 0


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    resume_text:      str,
    skills:           list[str],
    interests:        list[str],
    years_experience: float,
    education_level:  str,
    result:           RecommendationResult,
) -> str:
    top5 = result.top_roles[:5]
    top5_summary = []
    for i, rs in enumerate(top5, 1):
        role = ROLES[rs.role_key]
        top5_summary.append({
            "rank":              i,
            "role":              rs.role_title,
            "role_key":          rs.role_key,
            "suitability":       rs.overall_score,
            "skill_match":       rs.skill_score,
            "interest_match":    rs.interest_score,
            "matched_skills":    rs.matched_skill_keywords[:6],
            "matched_interests": rs.matched_interest_keywords[:4],
            "salary_inr": {
                "fresher": role.salary_fresher_inr,
                "mid":     role.salary_mid_inr,
                "senior":  role.salary_senior_inr,
            },
            "salary_global_usd": role.salary_global_usd,
            "demand_growth":     f"{role.demand_growth_pct}% YoY",
            "outlook":           role.five_year_outlook,
            "top_companies":     list(role.top_companies[:5]),
            "related_roles":     list(role.related_roles[:3]),
        })

    return f"""You are a world-class career strategist and AI-powered career coach. You help ambitious students and professionals navigate their careers with personalised, evidence-based guidance.

## CANDIDATE PROFILE
- Skills: {json.dumps(skills[:25])}
- Interests: {json.dumps(interests[:15])}
- Years of Experience: {years_experience}
- Education: {education_level}

## TOP 5 RECOMMENDED ROLES (algorithmically ranked — trust these scores)
{json.dumps(top5_summary, indent=2)}

## DOMAIN FIT OVERVIEW
{json.dumps(result.domain_fit)}
Best Fit Domain: {result.best_domain}

## RESUME EXCERPT (first 1500 chars)
---
{resume_text[:1500]}
---

## OUTPUT: Return a SINGLE valid JSON object (no markdown fences, no explanation):

{{
  "career_narrative": "3-4 sentences personalised to THIS candidate. Reference their specific skills and background. Be honest about strengths and realistic about gaps. End with an inspiring but grounded direction.",

  "personality_profile": {{
    "work_style": "1-2 sentences describing their likely work style based on their skills and interests",
    "strengths": ["specific strength 1", "specific strength 2", "specific strength 3"],
    "growth_areas": ["area 1", "area 2"],
    "ideal_environment": "short description of the team/company environment where they'd thrive"
  }},

  "role_details": [
    {{
      "role_key": "exact key from the ranked list above",
      "why_suited": "2-3 sentences explaining WHY this specific candidate suits this role — cite their actual skills",
      "what_youll_do": "2 sentences describing day-to-day responsibilities that would excite them",
      "skill_gaps": ["specific skill 1 they're missing for this role", "skill 2"],
      "salary_journey": {{
        "fresher_inr":  "₹X–Y LPA",
        "mid_inr":      "₹X–Y LPA (2–5 years)",
        "senior_inr":   "₹X–Y LPA (5+ years)",
        "global_usd":   "$X–Y/year",
        "note": "1 sentence salary context for Indian market"
      }},
      "transition_timeline": "e.g. Ready now | 2-3 months prep | 6-12 months reskilling"
    }}
  ],

  "market_trends": {{
    "hot_skills_2025": ["skill1", "skill2", "skill3", "skill4", "skill5"],
    "rising_domains": ["domain1", "domain2"],
    "india_specific_insight": "2 sentences about the Indian job market for this candidate's profile",
    "remote_opportunities": "1 sentence about remote/global opportunities for their top role"
  }},

  "action_plan": {{
    "week_1_2": ["specific action 1", "specific action 2"],
    "month_1": ["action 1", "action 2", "action 3"],
    "month_3": ["action 1", "action 2"],
    "month_6": ["action 1", "action 2"],
    "immediate_wins": ["do today 1", "do today 2"]
  }},

  "industry_insights": "2-3 sentences about what companies are hiring for in their top domain right now — be specific and current."
}}

## RULES
1. role_details must have exactly {min(5, len(top5))} entries, in rank order, using the exact role_keys provided.
2. why_suited must reference THIS candidate's actual skills — no generic advice.
3. skill_gaps: list ONLY 2-3 most critical missing skills for that role.
4. action_plan actions must be concrete and measurable, not vague ("Build a FastAPI project deployed to AWS" not "Learn cloud").
5. Be direct, honest, and specific. No corporate fluff.

## ANTI-HALLUCINATION RULES (CRITICAL)
6. The TOP 5 RECOMMENDED ROLES list above (with suitability scores, matched_skills, and
   matched_interests) is computed deterministically by an algorithm — treat it as ground truth.
   NEVER change the ranking, NEVER invent a 6th role, NEVER alter the suitability_score numbers.
7. why_suited must cite skills from the candidate's actual "Skills" list provided above —
   do not claim they have a skill that is not in that list.
8. skill_gaps must come from comparing the role's real requirements against the candidate's
   actual skills — do not invent generic gaps like "needs more experience" without specifics.
9. If the resume excerpt does not provide enough detail to say something specific about the
   candidate's background, say "Not found in the provided resume" rather than guessing."""


# ── Mock for dev mode ─────────────────────────────────────────────────────────

def _mock_response() -> str:
    return json.dumps({
        "career_narrative": "Configure LLM provider API key for personalised AI narrative.",
        "personality_profile": {
            "work_style": "Set GROQ_API_KEY in .env to see personalised profile.",
            "strengths": ["Configure LLM provider"],
            "growth_areas": ["Set GROQ_API_KEY"],
            "ideal_environment": "N/A — configure provider first",
        },
        "role_details": [],
        "market_trends": {
            "hot_skills_2025": ["AI/ML", "Cloud", "Python"],
            "rising_domains": ["AI", "Cloud"],
            "india_specific_insight": "Configure LLM provider for market insights.",
            "remote_opportunities": "Configure LLM provider.",
        },
        "action_plan": {
            "week_1_2": ["Set GROQ_API_KEY in .env"],
            "month_1":  ["Configure LLM API"],
            "month_3":  ["See personalised plan after configuration"],
            "month_6":  ["Configure provider first"],
            "immediate_wins": ["Set GROQ_API_KEY in your .env file"],
        },
        "industry_insights": "Configure LLM provider in .env for industry insights.",
    })


# ── Main agent entrypoint ─────────────────────────────────────────────────────

def run_career_recommendation(
    resume_text:      str,
    skills:           list[str],
    interests:        list[str],
    years_experience: float,
    education_level:  str,
) -> CareerRecommendationOutput:
    """
    Full career recommendation pipeline:
      1. Augment skills from resume text (NLP)
      2. Score all 20 roles (deterministic)
      3. Enrich top 5 via centralised LLM provider
      4. Merge and return
    """
    t0 = time.monotonic()

    # 1. Augment skills from resume text
    if resume_text:
        from app.utils.nlp_extractor import _extract_skills
        nlp_skills = [s["name"] for s in _extract_skills(resume_text)]
        skills     = list({*skills, *nlp_skills})

    logger.info("career_rec_start", skills=len(skills), interests=len(interests),
                years=years_experience, education=education_level)

    # 2. Score all roles (deterministic)
    result = score_all_roles(
        candidate_skills=skills,
        interests=interests,
        years_experience=years_experience,
        education_level=education_level,
        resume_text=resume_text,
    )

    # 3. LLM enrichment via centralised provider
    prompt = _build_prompt(
        resume_text, skills, interests, years_experience, education_level, result
    )
    try:
        raw, tokens = call_llm(prompt, temperature=0.3, max_tokens=4096, json_mode=True)
    except RuntimeError:
        logger.warning("llm_provider_unavailable_career_rec_mock")
        raw, tokens = _mock_response(), 0

    llm_data = parse_llm_json(raw)
    if not isinstance(llm_data, dict):
        llm_data = {}

    # 4. Merge scores + LLM per-role details
    role_details_map = {
        rd["role_key"]: rd
        for rd in llm_data.get("role_details", [])
        if isinstance(rd, dict) and "role_key" in rd
    }

    recommended_roles: list[RecommendedRoleDetail] = []
    for i, rs in enumerate(result.top_roles[:5], 1):
        role  = ROLES[rs.role_key]
        llm_r = role_details_map.get(rs.role_key, {})
        recommended_roles.append(RecommendedRoleDetail(
            rank=i,
            role_key=rs.role_key,
            role_title=rs.role_title,
            role_icon=rs.role_icon,
            domain=rs.domain,
            suitability_score=rs.overall_score,
            suitability_label=rs.suitability_label,
            confidence=rs.confidence,
            skill_match_pct=rs.skill_score,
            interest_match_pct=rs.interest_score,
            why_suited=llm_r.get("why_suited", ""),
            what_youll_do=llm_r.get("what_youll_do", ""),
            skill_gaps=llm_r.get("skill_gaps", []),
            salary_journey=llm_r.get("salary_journey", {
                "fresher_inr": f"₹{role.salary_fresher_inr[0]}–{role.salary_fresher_inr[1]} LPA",
                "mid_inr":     f"₹{role.salary_mid_inr[0]}–{role.salary_mid_inr[1]} LPA",
                "senior_inr":  f"₹{role.salary_senior_inr[0]}–{role.salary_senior_inr[1]} LPA",
                "global_usd":  f"${role.salary_global_usd[0]:,}–${role.salary_global_usd[1]:,}/year",
            }),
            top_companies=list(role.top_companies[:5]),
            related_roles=list(role.related_roles[:3]),
            transition_timeline=llm_r.get("transition_timeline", ""),
        ))

    all_role_scores = [
        {
            "role_key":          rs.role_key,
            "role_title":        rs.role_title,
            "role_icon":         rs.role_icon,
            "domain":            rs.domain,
            "overall_score":     rs.overall_score,
            "skill_score":       rs.skill_score,
            "interest_score":    rs.interest_score,
            "suitability_label": rs.suitability_label,
        }
        for rs in result.all_scores
    ]

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "career_rec_complete",
        top_role=recommended_roles[0].role_key if recommended_roles else "N/A",
        ms=elapsed_ms,
        tokens=tokens,
        provider=settings.DEFAULT_LLM_PROVIDER,
    )

    return CareerRecommendationOutput(
        recommended_roles=recommended_roles,
        all_role_scores=all_role_scores,
        domain_fit=result.domain_fit,
        best_domain=result.best_domain,
        career_narrative=llm_data.get("career_narrative", ""),
        personality_profile=llm_data.get("personality_profile", {}),
        market_trends=llm_data.get("market_trends", {}),
        action_plan=llm_data.get("action_plan", {}),
        industry_insights=llm_data.get("industry_insights", ""),
        candidate_skills=skills[:30],
        candidate_interests=interests[:15],
        years_experience=years_experience,
        education_level=education_level,
        model_used=settings.active_model,
        tokens_consumed=tokens,
        processing_time_ms=elapsed_ms,
    )
