"""
app/api/v1/endpoints/interview.py
──────────────────────────────────
Interview Coach REST API:

  POST   /api/v1/interview/sessions              — start new session
  GET    /api/v1/interview/sessions              — list user sessions
  GET    /api/v1/interview/sessions/{id}         — get session + questions
  GET    /api/v1/interview/sessions/{id}/current-question
  POST   /api/v1/interview/sessions/{id}/answer  — submit answer → get eval
  POST   /api/v1/interview/sessions/{id}/complete — generate final report
  POST   /api/v1/interview/sessions/{id}/abandon
  GET    /api/v1/interview/sessions/{id}/report  — get final report
  GET    /api/v1/interview/companies             — list supported companies
"""
from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from typing import Any

from app.api.dependencies import CurrentUser, DBSession
from app.agents.interview_question_bank import COMPANY_PROFILES
from app.core.logging import get_logger
from app.models.interview import InterviewSession
from app.services.interview_service import (
    InterviewService,
    _serialise_question,
)

router = APIRouter(prefix="/interview", tags=["Interview Coach"])
logger = get_logger(__name__)


# ── Request schemas ───────────────────────────────────────────────────────────
class StartSessionRequest(BaseModel):
    mode:            str  = Field("hr", description="hr | technical | company_specific")
    difficulty:      str  = Field("medium", description="easy | medium | hard")
    target_role:     str | None = Field(None, max_length=150)
    target_company:  str | None = Field(None, max_length=150)
    total_questions: int  = Field(5, ge=1, le=15)
    resume_id:       int | None = None


class SubmitAnswerRequest(BaseModel):
    question_number:     int   = Field(..., ge=1)
    answer_text:         str   = Field(..., min_length=5, max_length=5000)
    time_taken_seconds:  int | None = Field(None, ge=0)


class APIResponse(BaseModel):
    success: bool = True
    message: str  = "OK"
    data:    Any  = None


# ── Supported companies ───────────────────────────────────────────────────────
@router.get(
    "/companies",
    response_model=APIResponse,
    summary="List supported companies for company-specific interviews",
)
def list_companies(current_user: CurrentUser) -> APIResponse:
    companies = [
        {
            "key":             key,
            "name":            p.name,
            "interview_style": p.interview_style,
            "hot_topics":      list(p.hot_topics[:4]),
            "tips":            list(p.tips[:3]),
        }
        for key, p in COMPANY_PROFILES.items()
    ]
    return APIResponse(data={"companies": companies, "total": len(companies)})


# ── Session lifecycle ─────────────────────────────────────────────────────────
@router.post(
    "/sessions",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new interview session",
)
def start_session(
    req:          StartSessionRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Creates a new interview session and generates all questions upfront.

    **mode** options:
    - `hr` — Behavioural + motivational questions
    - `technical` — DS&A, system design, core CS concepts
    - `company_specific` — Tailored to company's known interview style

    Returns the first question immediately so the UI can display it right away.
    """
    svc    = InterviewService(db)
    result = svc.start_session(
        user_id=current_user.user_id,
        mode=req.mode,
        difficulty=req.difficulty,
        target_role=req.target_role,
        target_company=req.target_company,
        total_questions=req.total_questions,
        resume_id=req.resume_id,
    )
    return APIResponse(message="Interview session started. Good luck!", data=result)


@router.get(
    "/sessions",
    response_model=APIResponse,
    summary="List the user's interview sessions",
)
def list_sessions(
    current_user: CurrentUser,
    db:           DBSession,
    limit:        int = Query(20, ge=1, le=50),
) -> APIResponse:
    svc      = InterviewService(db)
    sessions = svc.list_sessions(current_user.user_id, limit=limit)
    return APIResponse(data={
        "total":    len(sessions),
        "sessions": [_session_list_item(s) for s in sessions],
    })


@router.get(
    "/sessions/{session_id}",
    response_model=APIResponse,
    summary="Get full session details with all questions",
)
def get_session(
    session_id:   int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc     = InterviewService(db)
    session = svc.get_session(session_id, current_user.user_id)
    return APIResponse(data=_session_detail(session))


@router.get(
    "/sessions/{session_id}/current-question",
    response_model=APIResponse,
    summary="Get the next unanswered question in the session",
)
def get_current_question(
    session_id:   int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Returns the next unanswered question.
    If all questions are answered, returns `session_complete: true`.
    """
    svc    = InterviewService(db)
    result = svc.get_current_question(session_id, current_user.user_id)
    return APIResponse(data=result)


@router.post(
    "/sessions/{session_id}/answer",
    response_model=APIResponse,
    summary="Submit an answer and receive instant evaluation",
)
def submit_answer(
    session_id:   int,
    req:          SubmitAnswerRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Submit your answer for a question. Returns:

    - **scores**: confidence, technical, communication, relevance, completeness
    - **star_breakdown**: which STAR components were present
    - **strengths / weaknesses**: from Gemini (if API key configured)
    - **model_answer**: what a strong answer looks like
    - **improved_answer**: your answer, rewritten better
    - **session_complete**: true if this was the last question
    """
    svc    = InterviewService(db)
    result = svc.submit_answer(
        session_id=session_id,
        user_id=current_user.user_id,
        question_number=req.question_number,
        answer_text=req.answer_text,
        time_taken_seconds=req.time_taken_seconds,
    )
    return APIResponse(message="Answer evaluated.", data=result)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=APIResponse,
    summary="Generate the final performance report for the session",
)
def complete_session(
    session_id:   int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Generates and persists the full interview performance report.

    Returns:
    - Overall, technical, confidence, communication scores
    - Letter grade (A–F)
    - Readiness verdict
    - Executive summary
    - Strengths and weaknesses observed
    - Improvement tips with action plan
    - Per-question breakdown
    """
    svc    = InterviewService(db)
    result = svc.complete_session(session_id, current_user.user_id)
    return APIResponse(message="Interview complete! Report generated.", data=result)


@router.post(
    "/sessions/{session_id}/abandon",
    response_model=APIResponse,
    summary="Abandon an in-progress session",
)
def abandon_session(
    session_id:   int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    InterviewService(db).abandon_session(session_id, current_user.user_id)
    return APIResponse(message="Session abandoned.")


@router.get(
    "/sessions/{session_id}/report",
    response_model=APIResponse,
    summary="Get the final report for a completed session",
)
def get_report(
    session_id:   int,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    svc    = InterviewService(db)
    report = svc.get_report(session_id, current_user.user_id)
    session = svc.get_session(session_id, current_user.user_id)
    from app.services.interview_service import _serialise_report
    return APIResponse(data=_serialise_report(report, session))


# ── Serialisers ───────────────────────────────────────────────────────────────
def _session_list_item(s: InterviewSession) -> dict:
    return {
        "session_id":       s.session_id,
        "mode":             s.mode.value,
        "difficulty":       s.difficulty.value,
        "target_role":      s.target_role,
        "target_company":   s.target_company,
        "status":           s.status.value,
        "total_questions":  s.total_questions,
        "questions_answered": s.questions_asked,
        "started_at":       s.started_at,
        "ended_at":         s.ended_at,
        "overall_score":    s.report.overall_score if s.report else None,
        "grade":            s.report.grade if s.report else None,
    }


def _session_detail(s: InterviewSession) -> dict:
    return {
        **_session_list_item(s),
        "questions": [_serialise_question(q) for q in s.questions],
    }
