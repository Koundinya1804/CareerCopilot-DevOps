"""
app/agents/recommendation_engine.py
─────────────────────────────────────
Multi-signal career recommendation scoring algorithm.

Algorithm: Weighted Multi-Signal Scoring
─────────────────────────────────────────
Score(role) = (skill_score × 0.45)
            + (interest_score × 0.30)
            + (experience_score × 0.15)
            + (education_bonus × 0.10)

Each sub-score is 0–100. Final score normalised to 0–100.

Skill Scoring:
  - Exact keyword match in candidate skills: +weight
  - Alias/fuzzy match:                       +weight × 0.8
  - Keyword appears in resume text:          +weight × 0.5
  - Bonus for critical role skills matched:  +5 per skill

Interest Scoring:
  - Each interest keyword match: +10 pts, capped at 100

Experience Scoring:
  - Gaussian curve centred on ideal_years for the role
  - Peak at ideal_years, tails off for fresher or over-experienced

Education Bonus:
  - PhD:      +10
  - Masters:  +7
  - Bachelors:+5
  - Diploma:  +2
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from app.agents.career_role_catalogue import ROLES, CareerRole, ROLE_DISPLAY_ORDER


@dataclass
class RoleScore:
    role_key:      str
    role_title:    str
    role_icon:     str
    domain:        str

    # Sub-scores (0–100 each)
    overall_score:    float
    skill_score:      float
    interest_score:   float
    experience_score: float
    education_bonus:  float

    # Breakdown
    matched_skill_keywords: list[str] = field(default_factory=list)
    matched_interest_keywords: list[str] = field(default_factory=list)
    suitability_label: str = ""
    confidence: str = "medium"   # high | medium | low


@dataclass
class RecommendationResult:
    top_roles:        list[RoleScore]   # top 5 sorted by overall_score
    all_scores:       list[RoleScore]   # all 20 roles sorted
    candidate_summary: dict             # extracted profile summary
    domain_fit:       dict              # domain → avg score
    best_domain:      str


# ── Normaliser helpers ─────────────────────────────────────────────────────────
def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


def _tokenise(text: str) -> set[str]:
    return {w for w in _normalise(text).split() if len(w) > 2}


# ── Experience score (Gaussian) ────────────────────────────────────────────────
def _experience_score(years: float, role: CareerRole) -> float:
    """
    Gaussian curve: peaks at ideal_years, score = 100 at peak.
    σ chosen so that ±3 years from ideal gives ~50% score.
    """
    if role.min_years > 0 and years < role.min_years:
        # Insufficient experience — penalise but don't zero out
        deficit = role.min_years - years
        return max(10.0, 50.0 - deficit * 15)

    sigma = max(1.5, role.ideal_years * 0.6)
    raw   = 100.0 * math.exp(-((years - role.ideal_years) ** 2) / (2 * sigma ** 2))
    return round(raw, 2)


# ── Education bonus ────────────────────────────────────────────────────────────
def _education_bonus(education_level: str) -> float:
    edu = education_level.lower()
    if "phd" in edu or "doctor" in edu:
        return 10.0
    if "master" in edu or "m.tech" in edu or "mba" in edu:
        return 7.0
    if "bachelor" in edu or "b.tech" in edu or "b.e" in edu:
        return 5.0
    if "diploma" in edu:
        return 2.0
    return 3.0


# ── Skill score ────────────────────────────────────────────────────────────────
def _skill_score(
    candidate_skills: list[str],
    resume_text:      str,
    role:             CareerRole,
) -> tuple[float, list[str]]:
    """
    Return (score 0–100, list of matched keyword names).
    """
    if not role.skill_keywords:
        return 50.0, []

    cand_tokens    = {_normalise(s) for s in candidate_skills}
    resume_tokens  = _tokenise(resume_text)
    matched:       list[str] = []
    score          = 0.0
    max_per_kw     = 100.0 / len(role.skill_keywords)

    for kw in role.skill_keywords:
        kw_n = _normalise(kw)
        kw_words = set(kw_n.split())

        # Exact match in skills list
        if kw_n in cand_tokens:
            score  += max_per_kw
            matched.append(kw)
        # Word overlap match in skills list (≥ 60% overlap)
        elif any(len(kw_words & set(s.split())) / max(len(kw_words), 1) >= 0.6
                 for s in cand_tokens):
            score  += max_per_kw * 0.85
            matched.append(kw)
        # Resume text mention
        elif kw_n in resume_tokens or any(w in resume_tokens for w in kw_words):
            score  += max_per_kw * 0.5
            matched.append(kw + " (resume)")

    return round(min(score, 100.0), 2), matched


# ── Interest score ─────────────────────────────────────────────────────────────
def _interest_score(
    interests:   list[str],
    role:        CareerRole,
) -> tuple[float, list[str]]:
    if not interests or not role.interest_keywords:
        return 30.0, []   # neutral score when no interests provided

    int_tokens = {_normalise(i) for i in interests}
    matched    = []
    score      = 0.0
    pts_each   = 100.0 / len(role.interest_keywords)

    for kw in role.interest_keywords:
        kw_n = _normalise(kw)
        kw_w = set(kw_n.split())
        if kw_n in int_tokens or any(
            len(kw_w & set(t.split())) / max(len(kw_w), 1) >= 0.6
            for t in int_tokens
        ):
            score  += pts_each
            matched.append(kw)

    return round(min(score, 100.0), 2), matched


# ── Suitability label ──────────────────────────────────────────────────────────
def _suitability_label(score: float) -> str:
    if score >= 80: return "Excellent Fit"
    if score >= 65: return "Strong Fit"
    if score >= 50: return "Good Fit"
    if score >= 35: return "Possible Fit"
    return "Low Fit"


def _confidence(matched_skills: int, matched_interests: int) -> str:
    total = matched_skills + matched_interests
    if total >= 8:  return "high"
    if total >= 4:  return "medium"
    return "low"


# ── Main scorer ────────────────────────────────────────────────────────────────
def score_all_roles(
    candidate_skills:  list[str],
    interests:         list[str],
    years_experience:  float,
    education_level:   str,
    resume_text:       str = "",
) -> RecommendationResult:
    """
    Score all 20 roles and return ranked recommendation result.
    """
    all_scores: list[RoleScore] = []

    for role_key, role in ROLES.items():
        sk_score,  sk_matched  = _skill_score(candidate_skills, resume_text, role)
        int_score, int_matched = _interest_score(interests, role)
        exp_score              = _experience_score(years_experience, role)
        edu_bonus              = _education_bonus(education_level)

        overall = round(
            sk_score   * 0.45
            + int_score  * 0.30
            + exp_score  * 0.15
            + edu_bonus  * 0.10,
            2,
        )

        all_scores.append(RoleScore(
            role_key=role_key,
            role_title=role.title,
            role_icon=role.icon,
            domain=role.domain,
            overall_score=overall,
            skill_score=sk_score,
            interest_score=int_score,
            experience_score=exp_score,
            education_bonus=edu_bonus,
            matched_skill_keywords=[m for m in sk_matched if "(resume)" not in m][:10],
            matched_interest_keywords=int_matched[:6],
            suitability_label=_suitability_label(overall),
            confidence=_confidence(
                len([m for m in sk_matched if "(resume)" not in m]),
                len(int_matched),
            ),
        ))

    all_scores.sort(key=lambda r: r.overall_score, reverse=True)
    top_roles = all_scores[:5]

    # Domain aggregation
    domain_totals: dict[str, list[float]] = {}
    for rs in all_scores:
        domain_totals.setdefault(rs.domain, []).append(rs.overall_score)
    domain_fit = {
        d: round(sum(scores) / len(scores), 1)
        for d, scores in domain_totals.items()
    }
    best_domain = max(domain_fit, key=lambda d: domain_fit[d])

    return RecommendationResult(
        top_roles=top_roles,
        all_scores=all_scores,
        candidate_summary={
            "skills_count":    len(candidate_skills),
            "interests_count": len(interests),
            "years_experience": years_experience,
            "education_level": education_level,
        },
        domain_fit=domain_fit,
        best_domain=best_domain,
    )
