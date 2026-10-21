"""
app/api/v1/endpoints/resume.py
───────────────────────────────
Resume Analyzer API endpoints:

  POST   /api/v1/resume/upload                   — upload a resume file
  POST   /api/v1/resume/{resume_id}/analyse       — trigger AI analysis
  POST   /api/v1/resume/upload-and-analyse        — upload + analyse in one call
  GET    /api/v1/resume/                          — list user's resumes
  GET    /api/v1/resume/{resume_id}               — get resume metadata
  GET    /api/v1/resume/{resume_id}/report        — get latest analysis report
  GET    /api/v1/resume/report/{report_id}        — get report by ID
  PUT    /api/v1/resume/{resume_id}/primary       — mark as primary
  DELETE /api/v1/resume/{resume_id}               — delete resume
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, DBSession
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.resume import CareerReport, Resume
from app.schemas.resume import (
    APIResponse,
    ContactInfo,
    ExtractedCertification,
    ExtractedEducation,
    ExtractedExperience,
    ExtractedProject,
    ExtractedSkill,
    ImprovementSuggestion,
    ResumeAnalysisReport,
    ResumeListItem,
    ResumeUploadResponse,
    ScoreBreakdown,
)
from app.services.resume_service import ResumeService

router = APIRouter(prefix="/resume", tags=["Resume Analyzer"])
logger = get_logger(__name__)


# ── Dependency ─────────────────────────────────────────────────────────────────
def get_resume_service(db: DBSession) -> ResumeService:
    return ResumeService(db)


# ── Upload ─────────────────────────────────────────────────────────────────────
@router.post(
    "/upload",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a resume file (PDF or DOCX)",
)
async def upload_resume(
    current_user:  CurrentUser,
    db:            DBSession,
    file:          UploadFile = File(..., description="PDF or DOCX resume file, max 10 MB"),
    make_primary:  bool       = Form(True, description="Set as the user's primary resume"),
) -> APIResponse:
    """
    Upload a resume file. Returns the resume_id which you can then pass to
    `/analyse` to trigger the AI analysis pipeline.
    """
    svc    = ResumeService(db)
    resume = await svc.upload_resume(current_user.user_id, file, make_primary)
    return APIResponse(
        message="Resume uploaded successfully. Call /analyse to run AI analysis.",
        data=ResumeUploadResponse(
            resume_id=resume.resume_id,
            filename=resume.filename,
            status=resume.status.value,
            message="Ready for analysis",
        ),
    )


# ── Analyse ────────────────────────────────────────────────────────────────────
@router.post(
    "/{resume_id}/analyse",
    response_model=APIResponse,
    summary="Trigger AI analysis for an uploaded resume",
)
async def analyse_resume(
    resume_id:     int,
    current_user:  CurrentUser,
    db:            DBSession,
    target_role:   str | None = Query(None, description="Optional target job role for tailored scoring"),
) -> APIResponse:
    """
    Run the full Resume Analyser Agent pipeline on an already-uploaded resume:

    1. Extract text from PDF/DOCX
    2. NLP entity extraction (skills, projects, certs)
    3. ATS score calculation (rule-based)
    4. Gemini AI enrichment and narrative generation
    5. Persist and return the structured report
    """
    svc    = ResumeService(db)
    report = await svc.analyse_resume(resume_id, current_user.user_id, target_role)
    return APIResponse(
        message="Analysis complete.",
        data=_build_report_response(report, db, resume_id, current_user.user_id),
    )


# ── Upload + Analyse (convenience endpoint) ────────────────────────────────────
@router.post(
    "/upload-and-analyse",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and immediately analyse a resume in one request",
)
async def upload_and_analyse(
    current_user:  CurrentUser,
    db:            DBSession,
    file:          UploadFile = File(...),
    target_role:   str | None = Form(None, description="Target job role for tailored ATS scoring"),
    make_primary:  bool       = Form(True),
) -> APIResponse:
    """
    Single-call convenience endpoint: upload + full AI analysis.
    Ideal for the frontend 'Drop resume here' flow.
    """
    svc    = ResumeService(db)
    resume = await svc.upload_resume(current_user.user_id, file, make_primary)
    report = await svc.analyse_resume(resume.resume_id, current_user.user_id, target_role)

    return APIResponse(
        message="Resume uploaded and analysed successfully.",
        data=_build_report_response(report, db, resume.resume_id, current_user.user_id),
    )


# ── List Resumes ───────────────────────────────────────────────────────────────
@router.get(
    "/",
    response_model=APIResponse,
    summary="List all resumes for the current user",
)
def list_resumes(
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc     = ResumeService(db)
    resumes = svc.list_resumes(current_user.user_id)
    latest_reports = svc.get_latest_reports_for_resumes(
        [r.resume_id for r in resumes], current_user.user_id
    )
    items   = []
    for r in resumes:
        latest = latest_reports.get(r.resume_id)
        items.append({
            "resume_id":  r.resume_id,
            "filename":   r.filename,
            "status":     r.status.value,
            "is_primary": bool(r.is_primary),
            "ats_score":  float(latest.ats_score) if latest else None,
            "page_count": r.page_count,
            "created_at": r.created_at,
        })
    return APIResponse(data={"total": len(items), "resumes": items})


# ── Get Resume Metadata ────────────────────────────────────────────────────────
@router.get(
    "/{resume_id}",
    response_model=APIResponse,
    summary="Get resume file metadata",
)
def get_resume(
    resume_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc    = ResumeService(db)
    resume = svc._get_resume_or_404(resume_id, current_user.user_id)
    return APIResponse(data={
        "resume_id":       resume.resume_id,
        "filename":        resume.filename,
        "status":          resume.status.value,
        "is_primary":      bool(resume.is_primary),
        "file_size_bytes": resume.file_size_bytes,
        "page_count":      resume.page_count,
        "created_at":      resume.created_at,
    })


# ── Get Latest Report ──────────────────────────────────────────────────────────
@router.get(
    "/{resume_id}/report",
    response_model=APIResponse,
    summary="Get the latest AI analysis report for a resume",
)
def get_resume_report(
    resume_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc    = ResumeService(db)
    report = svc.get_latest_report(resume_id, current_user.user_id)
    if not report:
        raise NotFoundError("CareerReport for resume", resume_id)
    return APIResponse(data=_build_report_response(report, db, resume_id, current_user.user_id))


# ── Get Report by ID ───────────────────────────────────────────────────────────
@router.get(
    "/report/{report_id}",
    response_model=APIResponse,
    summary="Get a specific analysis report by report_id",
)
def get_report_by_id(
    report_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc    = ResumeService(db)
    report = svc.get_report(report_id, current_user.user_id)
    return APIResponse(data=_build_report_response(report, db, report.resume_id, current_user.user_id))


# ── Set Primary ────────────────────────────────────────────────────────────────
@router.put(
    "/{resume_id}/primary",
    response_model=APIResponse,
    summary="Set a resume as the user's primary resume",
)
def set_primary_resume(
    resume_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc    = ResumeService(db)
    resume = svc.set_primary(resume_id, current_user.user_id)
    return APIResponse(message=f"Resume '{resume.filename}' is now your primary resume.")


# ── Delete Resume ──────────────────────────────────────────────────────────────
@router.delete(
    "/{resume_id}",
    response_model=APIResponse,
    summary="Delete a resume and all its reports",
)
def delete_resume(
    resume_id:    int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc = ResumeService(db)
    svc.delete_resume(resume_id, current_user.user_id)
    return APIResponse(message="Resume deleted successfully.")


# ── Response builder ───────────────────────────────────────────────────────────
def _build_report_response(
    report:    CareerReport,
    db:        Session,
    resume_id: int,
    user_id:   int,
) -> dict:
    """Convert a CareerReport ORM object into the full API response dict."""
    from sqlalchemy import select
    resume = db.scalar(select(Resume).where(Resume.resume_id == resume_id))

    return {
        "report_id":  report.report_id,
        "resume_id":  report.resume_id,
        "user_id":    report.user_id,
        "filename":   resume.filename if resume else "",

        "scores": {
            "ats_score":        float(report.ats_score),
            "formatting_score": float(report.formatting_score),
            "content_score":    float(report.content_score),
            "keyword_score":    float(report.keyword_score),
            "experience_score": float(report.experience_score),
            "grade":            _score_to_grade(float(report.ats_score)),
            "verdict":          _build_verdict(float(report.ats_score)),
        },

        "contact_info":           report.contact_info      or {},
        "skills":                 report.extracted_skills  or [],
        "technical_skills": [
            s["name"] for s in (report.extracted_skills or [])
            if s.get("category") != "soft"
        ],
        "soft_skills": [
            s["name"] for s in (report.extracted_skills or [])
            if s.get("category") == "soft"
        ],
        "projects":               report.extracted_projects  or [],
        "certifications":         report.extracted_certs     or [],
        "education":              report.extracted_education  or [],
        "experience":             report.extracted_experience or [],
        "total_years_experience": 0.0,  # populated from extracted_experience if needed

        "summary":            report.summary           or "",
        "strengths":          report.strengths         or [],
        "improvements":       report.improvements      or [],
        "keywords_found":     report.keywords_found    or [],
        "keywords_missing":   report.keywords_missing  or [],
        "seniority_match":    report.seniority_match.value if report.seniority_match else "undetected",
        "seniority_detected": None,

        "page_count":         resume.page_count   if resume else 0,
        "word_count":         0,
        "model_used":         report.model_used          or "",
        "processing_time_ms": report.processing_time_ms  or 0,
        "created_at":         report.created_at,
    }


def _score_to_grade(score: float) -> str:
    if score >= 85: return "A"
    if score >= 70: return "B"
    if score >= 55: return "C"
    if score >= 40: return "D"
    return "F"


def _build_verdict(score: float) -> str:
    if score >= 85: return "Excellent — highly ATS-compatible. Strong chance of passing screening."
    if score >= 70: return "Good — will likely pass ATS. Minor improvements recommended."
    if score >= 55: return "Fair — may pass ATS but needs targeted improvements."
    if score >= 40: return "Weak — likely to be filtered out. Significant revisions needed."
    return "Poor — needs a complete overhaul before submitting to ATS-enabled portals."
