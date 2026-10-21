"""
app/api/v1/endpoints/skill_gap.py
──────────────────────────────────
Skill Gap Analyzer REST API:

  GET  /api/v1/skill-gap/roles                     — list all supported roles
  GET  /api/v1/skill-gap/roles/{key}               — detail for one role
  POST /api/v1/skill-gap/analyse/resume            — analyse via resume_id
  POST /api/v1/skill-gap/analyse/text              — analyse via raw text
  POST /api/v1/skill-gap/compare                   — compare match % across roles
  GET  /api/v1/skill-gap/reports                   — list user's past reports
  GET  /api/v1/skill-gap/reports/{id}              — get one report
  DELETE /api/v1/skill-gap/reports/{id}            — delete a report
"""
from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DBSession
from app.agents.role_skill_db import ROLE_DISPLAY_ORDER, ROLE_REGISTRY, get_role
from app.models.skill_gap import SkillGapReport
from app.schemas.skill_gap import (
    AnalyseFromResumeRequest,
    AnalyseFromTextRequest,
    APIResponse,
    CompareRolesRequest,
    RoleComparisonItem,
    RoleComparisonResponse,
    RoleInfoResponse,
    ScoreSummary,
    SkillGapReportResponse,
    MissingSkillOut,
    MatchedSkillOut,
    score_to_grade,
    score_to_readiness,
)
from app.services.skill_gap_service import SkillGapService

router = APIRouter(prefix="/skill-gap", tags=["Skill Gap Analyzer"])


# ── Dependency ────────────────────────────────────────────────────────────────
def _svc(db: DBSession) -> SkillGapService:
    return SkillGapService(db)


# ── Role catalogue ────────────────────────────────────────────────────────────
@router.get(
    "/roles",
    response_model=APIResponse,
    summary="List all supported target roles",
)
def list_roles(current_user: CurrentUser) -> APIResponse:
    """Returns the 6 supported career roles with skill counts and salary ranges."""
    roles = []
    for key in ROLE_DISPLAY_ORDER:
        r = ROLE_REGISTRY[key]
        roles.append({
            "key":                 r.key,
            "title":               r.title,
            "icon":                r.icon,
            "description":         r.description,
            "salary_range_inr":    r.salary_range_inr,
            "avg_years_to_role":   r.avg_years_to_role,
            "required_skill_count": len(r.required_skills),
            "preferred_skill_count": len(r.preferred_skills),
            "top_required_skills": [s.name for s in r.required_skills
                                    if s.priority.value == "critical"][:5],
            "career_path":         list(r.career_path),
        })
    return APIResponse(data={"roles": roles, "total": len(roles)})


@router.get(
    "/roles/{role_key}",
    response_model=APIResponse,
    summary="Get detailed skill requirements for a specific role",
)
def get_role_detail(role_key: str, current_user: CurrentUser) -> APIResponse:
    """
    Returns the full skill database for a role including required skills,
    preferred skills, certifications, tools, and career path.
    """
    from app.core.exceptions import ValidationError
    try:
        r = get_role(role_key)
    except ValueError as e:
        raise ValidationError(str(e))

    return APIResponse(data={
        "key":                 r.key,
        "title":               r.title,
        "icon":                r.icon,
        "description":         r.description,
        "salary_range_inr":    r.salary_range_inr,
        "avg_years_to_role":   r.avg_years_to_role,
        "career_path":         list(r.career_path),
        "certifications":      list(r.certifications),
        "tools":               list(r.tools),
        "soft_skills":         list(r.soft_skills),
        "required_skills": [
            {
                "name":            s.name,
                "priority":        s.priority.value,
                "min_proficiency": s.min_proficiency.value,
                "category":        s.category,
                "description":     s.description,
            }
            for s in r.required_skills
        ],
        "preferred_skills": [
            {
                "name":            s.name,
                "priority":        s.priority.value,
                "min_proficiency": s.min_proficiency.value,
                "category":        s.category,
            }
            for s in r.preferred_skills
        ],
    })


# ── Analysis endpoints ────────────────────────────────────────────────────────
@router.post(
    "/analyse/resume",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyse skill gap from an uploaded resume",
)
def analyse_from_resume(
    req:          AnalyseFromResumeRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Full Skill Gap Analysis pipeline:

    1. Load resume text from DB (resume must be analysed first)
    2. Extract skills using NLP
    3. Match against role skill database (deterministic scoring)
    4. Gemini AI generates learning roadmap, course recommendations, projects
    5. Persist and return structured report

    **role_key** options: `ai_engineer`, `ml_engineer`, `data_scientist`,
    `java_developer`, `fullstack_developer`, `cloud_engineer`
    """
    svc    = SkillGapService(db)
    report = svc.analyse_from_resume(
        user_id=current_user.user_id,
        resume_id=req.resume_id,
        role_key=req.role_key,
        target_company=req.target_company,
        extra_skills=req.extra_skills,
    )
    return APIResponse(
        message="Skill gap analysis complete.",
        data=_build_response(report),
    )


@router.post(
    "/analyse/text",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyse skill gap from pasted resume text",
)
def analyse_from_text(
    req:          AnalyseFromTextRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Same pipeline as `/analyse/resume` but accepts raw resume text directly.
    Useful for quick analysis without uploading a file.
    """
    svc    = SkillGapService(db)
    report = svc.analyse_from_text(
        user_id=current_user.user_id,
        resume_text=req.resume_text,
        role_key=req.role_key,
        target_company=req.target_company,
        extra_skills=req.extra_skills,
    )
    return APIResponse(
        message="Skill gap analysis complete.",
        data=_build_response(report),
    )


# ── Role comparison ───────────────────────────────────────────────────────────
@router.post(
    "/compare",
    response_model=APIResponse,
    summary="Compare match % across multiple roles simultaneously",
)
def compare_roles(
    req:          CompareRolesRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Quickly compares how well a resume matches 2–6 target roles.
    Returns a sorted ranking. Does NOT consume Gemini tokens.

    Great for helping users decide which role to target first.
    """
    svc         = SkillGapService(db)
    comparisons = svc.compare_roles(
        user_id=current_user.user_id,
        resume_id=req.resume_id,
        role_keys=req.role_keys,
    )

    items = [
        RoleComparisonItem(
            role_key=c["role_key"],
            role_title=c["role_title"],
            overall_match_pct=c["overall_match_pct"],
            required_match_pct=c["required_match_pct"],
            gap_severity=c["gap_severity"],
            matched_count=c["matched_count"],
            missing_critical=c["missing_critical"],
            grade=score_to_grade(c["overall_match_pct"]),
        )
        for c in comparisons
    ]

    return APIResponse(
        message=f"Compared {len(items)} roles.",
        data=RoleComparisonResponse(
            comparisons=items,
            best_fit=items[0].role_key if items else "",
            resume_id=req.resume_id,
        ),
    )


# ── Report CRUD ───────────────────────────────────────────────────────────────
@router.get(
    "/reports",
    response_model=APIResponse,
    summary="List all skill gap reports for the current user",
)
def list_reports(
    current_user: CurrentUser,
    db:           DBSession,
    role_key:     str | None = Query(None, description="Filter by role"),
    limit:        int        = Query(20, ge=1, le=100),
) -> APIResponse:
    svc     = SkillGapService(db)
    reports = svc.list_reports(current_user.user_id, role_key=role_key, limit=limit)
    return APIResponse(data={
        "total":   len(reports),
        "reports": [_build_list_item(r) for r in reports],
    })


@router.get(
    "/reports/{gap_report_id}",
    response_model=APIResponse,
    summary="Get a skill gap report by ID",
)
def get_report(
    gap_report_id: int,
    current_user:  CurrentUser,
    db:            DBSession,
) -> APIResponse:
    svc    = SkillGapService(db)
    report = svc.get_report(gap_report_id, current_user.user_id)
    return APIResponse(data=_build_response(report))


@router.delete(
    "/reports/{gap_report_id}",
    response_model=APIResponse,
    summary="Delete a skill gap report",
)
def delete_report(
    gap_report_id: int,
    current_user:  CurrentUser,
    db:            DBSession,
) -> APIResponse:
    SkillGapService(db).delete_report(gap_report_id, current_user.user_id)
    return APIResponse(message="Report deleted.")


# ── Response builders ─────────────────────────────────────────────────────────
def _build_response(r: SkillGapReport) -> dict:
    pct = float(r.overall_match_pct)
    return {
        "gap_report_id":  r.gap_report_id,
        "role_key":       r.target_role_key,
        "role_title":     r.target_role_title,
        "target_company": r.target_company,
        "scores": {
            "overall_match_pct":     pct,
            "required_match_pct":    float(r.required_match_pct),
            "preferred_match_pct":   float(r.preferred_match_pct),
            "gap_severity":          r.gap_severity.value,
            "estimated_prep_months": r.estimated_prep_months,
            "grade":                 score_to_grade(pct),
            "readiness_label":       score_to_readiness(pct),
        },
        "matched_skills":       r.matched_skills    or [],
        "missing_required":     r.missing_required  or [],
        "missing_preferred":    r.missing_preferred or [],
        "executive_summary":    r.executive_summary    or "",
        "detailed_feedback":    r.detailed_feedback    or "",
        "strengths":            r.strengths            or [],
        "learning_priorities":  r.learning_priorities  or [],
        "recommended_courses":  r.recommended_courses  or [],
        "recommended_projects": r.recommended_projects or [],
        "recommended_certs":    r.recommended_certs    or [],
        "quick_wins":           r.quick_wins           or [],
        "salary_insight":       r.salary_insight       or "",
        "model_used":           r.model_used           or "",
        "processing_time_ms":   r.processing_time_ms   or 0,
        "created_at":           r.created_at,
    }


def _build_list_item(r: SkillGapReport) -> dict:
    pct = float(r.overall_match_pct)
    return {
        "gap_report_id":       r.gap_report_id,
        "role_key":            r.target_role_key,
        "role_title":          r.target_role_title,
        "target_company":      r.target_company,
        "overall_match_pct":   pct,
        "gap_severity":        r.gap_severity.value,
        "grade":               score_to_grade(pct),
        "readiness_label":     score_to_readiness(pct),
        "estimated_prep_months": r.estimated_prep_months,
        "created_at":          r.created_at,
    }
