"""
app/api/v1/endpoints/career_recommendation.py
───────────────────────────────────────────────
Career Recommendation Agent REST API:

  GET  /api/v1/career/roles                    — browse all 20 roles in catalogue
  GET  /api/v1/career/roles/{key}              — detail for one role
  POST /api/v1/career/recommend/resume         — recommend from uploaded resume
  POST /api/v1/career/recommend/profile        — recommend from explicit inputs
  POST /api/v1/career/quick-compare           — fast score comparison (no Gemini)
  GET  /api/v1/career/reports                  — list user's past reports
  GET  /api/v1/career/reports/{id}             — get full report
  DELETE /api/v1/career/reports/{id}           — delete a report
"""
from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DBSession
from app.agents.career_role_catalogue import ROLE_DISPLAY_ORDER, ROLES
from app.schemas.career_recommendation import (
    APIResponse,
    CareerRecommendationResponse,
    QuickComparisonRequest,
    RecommendationListItem,
    RecommendFromProfileRequest,
    RecommendFromResumeRequest,
    RecommendedRoleOut,
    RoleScoreSummary,
)
from app.services.career_recommendation_service import CareerRecommendationService

router = APIRouter(prefix="/career", tags=["Career Recommendation"])


def _svc(db: DBSession) -> CareerRecommendationService:
    return CareerRecommendationService(db)


# ── Role Catalogue ────────────────────────────────────────────────────────────

@router.get(
    "/roles",
    response_model=APIResponse,
    summary="Browse all 20 career roles in the catalogue",
)
def list_roles(
    current_user: CurrentUser,
    domain: str | None = Query(None, description="Filter by domain"),
) -> APIResponse:
    """
    Returns all 20 supported career roles with salary ranges, demand growth,
    and top companies — useful for the role-exploration UI.
    """
    roles = []
    for key in ROLE_DISPLAY_ORDER:
        r = ROLES[key]
        if domain and r.domain.lower() != domain.lower():
            continue
        roles.append({
            "key":               r.key,
            "title":             r.title,
            "domain":            r.domain,
            "icon":              r.icon,
            "tagline":           r.tagline,
            "salary_mid_inr":    r.salary_mid_inr,
            "salary_senior_inr": r.salary_senior_inr,
            "demand_growth_pct": r.demand_growth_pct,
            "five_year_outlook": r.five_year_outlook,
            "remote_friendly":   r.remote_friendly,
            "top_companies":     list(r.top_companies[:4]),
            "related_roles":     list(r.related_roles[:3]),
            "min_years":         r.min_years,
            "ideal_years":       r.ideal_years,
        })

    domains = sorted({ROLES[k].domain for k in ROLE_DISPLAY_ORDER})
    return APIResponse(data={"roles": roles, "total": len(roles), "domains": domains})


@router.get(
    "/roles/{role_key}",
    response_model=APIResponse,
    summary="Get detailed info for a specific career role",
)
def get_role_detail(role_key: str, current_user: CurrentUser) -> APIResponse:
    from app.core.exceptions import ValidationError
    if role_key not in ROLES:
        raise ValidationError(f"Unknown role '{role_key}'. Valid: {list(ROLES)}")
    r = ROLES[role_key]
    return APIResponse(data={
        "key":                   r.key,
        "title":                 r.title,
        "domain":                r.domain,
        "icon":                  r.icon,
        "tagline":               r.tagline,
        "salary_fresher_inr":    r.salary_fresher_inr,
        "salary_mid_inr":        r.salary_mid_inr,
        "salary_senior_inr":     r.salary_senior_inr,
        "salary_global_usd":     r.salary_global_usd,
        "demand_growth_pct":     r.demand_growth_pct,
        "five_year_outlook":     r.five_year_outlook,
        "remote_friendly":       r.remote_friendly,
        "top_companies":         list(r.top_companies),
        "related_roles":         list(r.related_roles),
        "personality_traits":    list(r.personality_traits),
        "skill_keywords":        list(r.skill_keywords[:15]),
        "interest_keywords":     list(r.interest_keywords),
        "min_education":         r.min_education,
        "preferred_education":   r.preferred_education,
        "min_years":             r.min_years,
        "ideal_years":           r.ideal_years,
        "senior_years":          r.senior_years,
    })


# ── Recommendation Endpoints ──────────────────────────────────────────────────

@router.post(
    "/recommend/resume",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Get career recommendations from an uploaded resume",
)
def recommend_from_resume(
    req:          RecommendFromResumeRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Full 5-stage Career Recommendation pipeline:

    1. Load resume text from DB (resume must be analysed first)
    2. Extract skills via NLP + merge with extra_skills
    3. Score all 20 career roles using multi-signal algorithm
    4. Gemini generates personalised narrative, action plan, and insights
    5. Persist and return the structured report

    **interests**: List of domains/topics the candidate cares about.
    Examples: `["machine learning", "startups", "open source"]`
    """
    report = _svc(db).analyse_from_resume(
        user_id=current_user.user_id,
        resume_id=req.resume_id,
        interests=req.interests,
        extra_skills=req.extra_skills,
    )
    return APIResponse(
        message="Career recommendations generated.",
        data=_build_full_response(report),
    )


@router.post(
    "/recommend/profile",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Get career recommendations from an explicit profile input",
)
def recommend_from_profile(
    req:          RecommendFromProfileRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Same pipeline as `/recommend/resume` but accepts explicit inputs
    instead of loading a saved resume.

    Ideal for: quick demo, profile without a file upload, or manual override.

    **education_level**: `Bachelors` | `Masters` | `PhD` | `Diploma`
    """
    report = _svc(db).analyse_from_profile(
        user_id=current_user.user_id,
        skills=req.skills,
        interests=req.interests,
        years_experience=req.years_experience,
        education_level=req.education_level,
        resume_text=req.resume_text,
    )
    return APIResponse(
        message="Career recommendations generated.",
        data=_build_full_response(report),
    )


@router.post(
    "/quick-compare",
    response_model=APIResponse,
    summary="Fast role scoring without Gemini (no DB write, instant response)",
)
def quick_compare(
    req:          QuickComparisonRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Returns suitability scores for all 20 roles instantly without calling Gemini.
    Useful for real-time UI sliders / skill-picker interactions.
    Zero latency (no LLM call, no DB write).
    """
    scores = _svc(db).quick_comparison(
        skills=req.skills,
        interests=req.interests,
        years_experience=req.years_experience,
        education_level=req.education_level,
    )
    return APIResponse(
        data={
            "scores": scores,
            "total":  len(scores),
            "top_role": scores[0] if scores else None,
        },
    )


# ── Report CRUD ───────────────────────────────────────────────────────────────

@router.get(
    "/reports",
    response_model=APIResponse,
    summary="List the current user's career recommendation history",
)
def list_reports(
    current_user: CurrentUser,
    db:           DBSession,
    limit:        int = Query(10, ge=1, le=50),
) -> APIResponse:
    reports = _svc(db).list_reports(current_user.user_id, limit=limit)
    return APIResponse(data={
        "total":   len(reports),
        "reports": [_build_list_item(r) for r in reports],
    })


@router.get(
    "/reports/{report_id}",
    response_model=APIResponse,
    summary="Get a full career recommendation report by ID",
)
def get_report(
    report_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    report = _svc(db).get_report(report_id, current_user.user_id)
    return APIResponse(data=_build_full_response(report))


@router.delete(
    "/reports/{report_id}",
    response_model=APIResponse,
    summary="Delete a career recommendation report",
)
def delete_report(
    report_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    _svc(db).delete_report(report_id, current_user.user_id)
    return APIResponse(message="Report deleted.")


# ── Response builders ─────────────────────────────────────────────────────────

def _build_full_response(r) -> dict:
    rec_data   = r.recommended_roles or {}
    roles_list = rec_data.get("roles", []) if isinstance(rec_data, dict) else []
    all_scores = rec_data.get("all_scores", []) if isinstance(rec_data, dict) else []
    domain_fit = rec_data.get("domain_fit", {}) if isinstance(rec_data, dict) else {}
    best_domain = rec_data.get("best_domain", "") if isinstance(rec_data, dict) else ""

    industries = r.industry_insights
    if isinstance(industries, dict):
        industries = industries.get("text", "")

    return {
        "report_id":           r.report_id,
        "recommended_roles":   roles_list,
        "all_role_scores":     all_scores,
        "domain_fit":          domain_fit,
        "best_domain":         best_domain,
        "career_narrative":    r.career_narrative  or "",
        "personality_profile": r.personality_profile or {},
        "market_trends":       r.market_trends      or {},
        "action_plan":         r.action_plan        or {},
        "industry_insights":   industries           or "",
        "candidate_skills":    (r.input_skills or {}).get("skills", []),
        "candidate_interests": (r.input_interests or {}).get("interests", []),
        "years_experience":    float(r.input_experience_years or 0),
        "education_level":     r.input_education_level or "",
        "model_used":          r.model_used          or "",
        "processing_time_ms":  r.processing_time_ms  or 0,
        "created_at":          r.created_at,
    }


def _build_list_item(r) -> dict:
    rec_data    = r.recommended_roles or {}
    best_domain = rec_data.get("best_domain", "") if isinstance(rec_data, dict) else ""
    return {
        "report_id":            r.report_id,
        "top_recommended_role": r.top_recommended_role,
        "top_role_score":       float(r.top_role_score or 0),
        "best_domain":          best_domain,
        "created_at":           r.created_at,
    }
