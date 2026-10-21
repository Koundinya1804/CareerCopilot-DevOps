"""
app/schemas/career_recommendation.py
──────────────────────────────────────
Pydantic v2 schemas for the Career Recommendation Agent API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────

class RecommendFromResumeRequest(BaseModel):
    resume_id:    int
    interests:    list[str] = Field(
        default_factory=list,
        description="Domains/topics the user is passionate about",
        examples=[["machine learning", "ai products", "python"]],
    )
    extra_skills: list[str] = Field(
        default_factory=list,
        description="Skills to add on top of resume extraction",
    )


class RecommendFromProfileRequest(BaseModel):
    skills:           list[str] = Field(..., min_length=1,
                                        description="Explicit skill list")
    interests:        list[str] = Field(default_factory=list)
    years_experience: float     = Field(0.0, ge=0.0, le=50.0)
    education_level:  str       = Field("Bachelors",
                                        description="Bachelors | Masters | PhD | Diploma")
    resume_text:      str       = Field("", max_length=20000,
                                        description="Optional raw resume text for richer extraction")


class QuickComparisonRequest(BaseModel):
    skills:           list[str] = Field(..., min_length=1)
    interests:        list[str] = Field(default_factory=list)
    years_experience: float     = Field(0.0, ge=0.0, le=50.0)
    education_level:  str       = Field("Bachelors")


# ── Response sub-schemas ──────────────────────────────────────────────────────

class SalaryJourney(BaseModel):
    fresher_inr: str
    mid_inr:     str
    senior_inr:  str
    global_usd:  str
    note:        str = ""


class RecommendedRoleOut(BaseModel):
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
    why_suited:         str
    what_youll_do:      str
    skill_gaps:         list[str]
    salary_journey:     dict
    top_companies:      list[str]
    related_roles:      list[str]
    transition_timeline: str


class RoleScoreSummary(BaseModel):
    role_key:          str
    role_title:        str
    role_icon:         str
    domain:            str
    overall_score:     float
    suitability_label: str


class PersonalityProfile(BaseModel):
    work_style:       str
    strengths:        list[str]
    growth_areas:     list[str]
    ideal_environment: str


class MarketTrends(BaseModel):
    hot_skills_2025:        list[str]
    rising_domains:         list[str]
    india_specific_insight: str
    remote_opportunities:   str


class ActionPlan(BaseModel):
    immediate_wins: list[str]
    week_1_2:       list[str]
    month_1:        list[str]
    month_3:        list[str]
    month_6:        list[str]


# ── Full report response ──────────────────────────────────────────────────────

class CareerRecommendationResponse(BaseModel):
    report_id:           int
    recommended_roles:   list[RecommendedRoleOut]
    all_role_scores:     list[RoleScoreSummary]
    domain_fit:          dict
    best_domain:         str
    career_narrative:    str
    personality_profile: dict
    market_trends:       dict
    action_plan:         dict
    industry_insights:   str
    candidate_skills:    list[str]
    candidate_interests: list[str]
    years_experience:    float
    education_level:     str
    model_used:          str
    processing_time_ms:  int
    created_at:          datetime

    model_config = {"from_attributes": True}


# ── List item ─────────────────────────────────────────────────────────────────

class RecommendationListItem(BaseModel):
    report_id:            int
    top_recommended_role: str | None
    top_role_score:       float
    best_domain:          str | None
    created_at:           datetime

    model_config = {"from_attributes": True}


# ── Standard envelope ─────────────────────────────────────────────────────────

class APIResponse(BaseModel):
    success: bool = True
    message: str  = "OK"
    data:    Any  = None
