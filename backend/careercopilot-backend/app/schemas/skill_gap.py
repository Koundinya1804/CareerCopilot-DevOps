"""
app/schemas/skill_gap.py
─────────────────────────
Pydantic v2 schemas for Skill Gap Analyzer API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────

class AnalyseFromResumeRequest(BaseModel):
    resume_id:      int
    role_key:       str           = Field(..., description="e.g. ai_engineer, ml_engineer")
    target_company: str | None    = Field(None, max_length=150)
    extra_skills:   list[str]     = Field(default_factory=list,
                                          description="Additional skills not in resume")


class AnalyseFromTextRequest(BaseModel):
    resume_text:    str           = Field(..., min_length=50, max_length=20000)
    role_key:       str
    target_company: str | None    = None
    extra_skills:   list[str]     = Field(default_factory=list)


class CompareRolesRequest(BaseModel):
    resume_id:  int
    role_keys:  list[str] = Field(..., min_length=2, max_length=6,
                                   description="2–6 role keys to compare")


# ── Sub-schemas ───────────────────────────────────────────────────────────────

class MatchedSkillOut(BaseModel):
    name:           str
    candidate_name: str
    priority:       str
    category:       str
    match_type:     str


class MissingSkillOut(BaseModel):
    name:            str
    priority:        str
    category:        str
    min_proficiency: str
    description:     str
    learning_url:    str


class LearningPriority(BaseModel):
    rank:        int
    skill:       str
    why:         str
    time_weeks:  int
    approach:    str


class CourseRecommendation(BaseModel):
    title:          str
    platform:       str
    url:            str
    skill_covered:  str
    duration_weeks: int
    is_free:        bool
    priority:       str


class ProjectRecommendation(BaseModel):
    title:            str
    description:      str
    skills_covered:   list[str]
    difficulty:       str
    estimated_hours:  int


class CertRecommendation(BaseModel):
    name:              str
    issuer:            str
    why:               str
    estimated_months:  int
    cost_usd:          float


class QuickWin(BaseModel):
    action:    str
    impact:    str
    time_days: int


class ScoreSummary(BaseModel):
    overall_match_pct:     float
    required_match_pct:    float
    preferred_match_pct:   float
    gap_severity:          str
    estimated_prep_months: int
    grade:                 str
    readiness_label:       str


# ── Full report response ──────────────────────────────────────────────────────

class SkillGapReportResponse(BaseModel):
    gap_report_id:         int
    role_key:              str
    role_title:            str
    target_company:        str | None
    scores:                ScoreSummary
    matched_skills:        list[MatchedSkillOut]
    missing_required:      list[MissingSkillOut]
    missing_preferred:     list[MissingSkillOut]
    executive_summary:     str
    detailed_feedback:     str
    strengths:             list[str]
    learning_priorities:   list[dict]
    recommended_courses:   list[dict]
    recommended_projects:  list[dict]
    recommended_certs:     list[dict]
    quick_wins:            list[dict]
    salary_insight:        str
    model_used:            str
    processing_time_ms:    int
    created_at:            datetime

    model_config = {"from_attributes": True}


# ── Comparison response ───────────────────────────────────────────────────────

class RoleComparisonItem(BaseModel):
    role_key:           str
    role_title:         str
    overall_match_pct:  float
    required_match_pct: float
    gap_severity:       str
    matched_count:      int
    missing_critical:   int
    grade:              str


class RoleComparisonResponse(BaseModel):
    comparisons:  list[RoleComparisonItem]
    best_fit:     str
    resume_id:    int


# ── Role info response ────────────────────────────────────────────────────────

class RoleInfoResponse(BaseModel):
    key:              str
    title:            str
    icon:             str
    description:      str
    salary_range_inr: tuple[int, int]
    avg_years_to_role: float
    career_path:      list[str]
    required_skill_count:  int
    preferred_skill_count: int
    top_required_skills:   list[str]
    certifications:        list[str]


# ── Standard envelope ─────────────────────────────────────────────────────────

class APIResponse(BaseModel):
    success: bool = True
    message: str  = "OK"
    data:    Any  = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def score_to_grade(pct: float) -> str:
    if pct >= 85: return "A"
    if pct >= 70: return "B"
    if pct >= 55: return "C"
    if pct >= 40: return "D"
    return "F"


def score_to_readiness(pct: float) -> str:
    if pct >= 90: return "Ready to Apply"
    if pct >= 70: return "Apply with Confidence"
    if pct >= 55: return "Apply After Short Prep"
    if pct >= 40: return "Needs Focused Preparation"
    if pct >= 25: return "Significant Upskilling Required"
    return "Consider a Different Entry Path"
