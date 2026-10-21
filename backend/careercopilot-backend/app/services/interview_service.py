"""
app/services/interview_service.py
──────────────────────────────────
Interview Coach business logic layer.

  start_session()         → create session, generate first question
  get_next_question()     → generate next question (or signal session end)
  submit_answer()         → evaluate answer, update question record
  complete_session()      → generate final report, mark session done
  get_session()           → fetch session with questions
  get_report()            → fetch report
  list_sessions()         → user's session history
  abandon_session()       → mark abandoned
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.interview_coach_agent import (
    AnswerFeedback,
    SessionReport,
    evaluate_answer_with_ai,
    generate_questions,
    generate_session_report,
)
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.llm_provider import get_last_call_usage
from app.models.agent_log import AgentName
from app.models.notification import NotificationType
from app.services.agent_log_service import timed_agent_call
from app.services.notification_service import notify
from app.core.logging import get_logger
from app.models.interview import (
    InterviewDifficulty,
    InterviewMode,
    InterviewQuestion,
    InterviewReport,
    InterviewSession,
    QuestionType,
    SessionStatus,
)
from app.models.resume import Resume

logger = get_logger(__name__)


class InterviewService:

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Start Session ─────────────────────────────────────────────────────────
    def start_session(
        self,
        user_id:        int,
        mode:           str,
        difficulty:     str,
        target_role:    str | None,
        target_company: str | None,
        total_questions: int,
        resume_id:      int | None,
    ) -> dict:
        """Create a new interview session and generate all questions upfront."""
        # Validate inputs
        try:
            mode_enum = InterviewMode(mode)
            diff_enum = InterviewDifficulty(difficulty)
        except ValueError:
            raise ValidationError(f"Invalid mode '{mode}' or difficulty '{difficulty}'.")

        if not 1 <= total_questions <= 15:
            raise ValidationError("total_questions must be between 1 and 15.")

        # Load resume text if provided
        resume_text = ""
        if resume_id:
            resume = self._db.scalar(
                select(Resume).where(Resume.resume_id == resume_id,
                                     Resume.user_id   == user_id)
            )
            if resume and resume.raw_text:
                resume_text = resume.raw_text

        # Create session
        session = InterviewSession(
            user_id=user_id,
            resume_id=resume_id,
            mode=mode_enum,
            difficulty=diff_enum,
            target_role=target_role,
            target_company=target_company,
            total_questions=total_questions,
            questions_asked=0,
            status=SessionStatus.IN_PROGRESS,
            model_used=settings.active_model,
        )
        self._db.add(session)
        self._db.flush()

        # Generate all questions at once
        with timed_agent_call(
            self._db, user_id=user_id, agent_name=AgentName.INTERVIEW_COACH,
            metadata={"session_id": session.session_id, "stage": "generate_questions"},
        ) as ctx:
            generated = generate_questions(
                mode=mode,
                n=total_questions,
                target_role=target_role,
                target_company=target_company,
                difficulty=difficulty,
                resume_text=resume_text,
                asked_so_far=[],
            )
            usage = get_last_call_usage()
            ctx["input_tokens"]  = usage.get("input_tokens")
            ctx["output_tokens"] = usage.get("output_tokens")

        for i, gq in enumerate(generated, 1):
            q = InterviewQuestion(
                session_id=session.session_id,
                question_number=i,
                question_text=gq.question_text,
                question_type=QuestionType(gq.question_type) if gq.question_type in QuestionType._value2member_map_ else QuestionType.HR,
                follow_up_hint=gq.follow_up_hint,
                difficulty_level=gq.difficulty,
            )
            self._db.add(q)

        self._db.flush()
        logger.info("session_started", session_id=session.session_id,
                    mode=mode, questions=total_questions)

        # Return first question
        first_q = self._db.scalar(
            select(InterviewQuestion).where(
                InterviewQuestion.session_id     == session.session_id,
                InterviewQuestion.question_number == 1,
            )
        )
        return {
            "session_id":       session.session_id,
            "mode":             mode,
            "difficulty":       difficulty,
            "target_role":      target_role,
            "target_company":   target_company,
            "total_questions":  total_questions,
            "current_question": _serialise_question(first_q) if first_q else None,
            "progress":         {"answered": 0, "total": total_questions},
        }

    # ── Get Next Question ─────────────────────────────────────────────────────
    def get_current_question(self, session_id: int, user_id: int) -> dict:
        session = self._get_session(session_id, user_id)
        next_num = session.questions_asked + 1

        if next_num > session.total_questions:
            return {
                "session_id":      session_id,
                "session_complete": True,
                "message":         "All questions answered. Call /complete to generate your report.",
                "progress":        {"answered": session.questions_asked, "total": session.total_questions},
            }

        q = self._db.scalar(
            select(InterviewQuestion).where(
                InterviewQuestion.session_id     == session_id,
                InterviewQuestion.question_number == next_num,
            )
        )
        return {
            "session_id":       session_id,
            "session_complete": False,
            "current_question": _serialise_question(q) if q else None,
            "progress":         {"answered": session.questions_asked, "total": session.total_questions},
        }

    # ── Submit Answer ─────────────────────────────────────────────────────────
    def submit_answer(
        self,
        session_id:    int,
        user_id:       int,
        question_number: int,
        answer_text:   str,
        time_taken_seconds: int | None = None,
    ) -> dict:
        session = self._get_session(session_id, user_id)

        if session.status != SessionStatus.IN_PROGRESS:
            raise ValidationError("Session is not in progress.")
        if not answer_text or len(answer_text.strip()) < 5:
            raise ValidationError("Answer is too short. Please provide a meaningful response.")

        q: InterviewQuestion | None = self._db.scalar(
            select(InterviewQuestion).where(
                InterviewQuestion.session_id     == session_id,
                InterviewQuestion.question_number == question_number,
            )
        )
        if not q:
            raise NotFoundError("InterviewQuestion", question_number)
        if q.user_answer:
            raise ValidationError(f"Question {question_number} has already been answered.")

        # Evaluate answer
        with timed_agent_call(
            self._db, user_id=user_id, agent_name=AgentName.INTERVIEW_COACH,
            metadata={"session_id": session_id, "stage": "evaluate_answer", "question_number": question_number},
        ) as ctx:
            feedback: AnswerFeedback = evaluate_answer_with_ai(
                question=q.question_text,
                answer=answer_text,
                question_type=q.question_type.value,
                target_role=session.target_role,
                topic=None,
            )
            usage = get_last_call_usage()
            ctx["input_tokens"]  = usage.get("input_tokens")
            ctx["output_tokens"] = usage.get("output_tokens")

        # Persist evaluation
        q.user_answer         = answer_text
        q.answer_score        = feedback.scores.overall_score
        q.confidence_score    = feedback.scores.confidence_score
        q.technical_score     = feedback.scores.technical_score
        q.communication_score = feedback.scores.communication_score
        q.relevance_score     = feedback.scores.relevance_score
        q.feedback_json       = feedback.qualitative
        q.model_answer        = feedback.model_answer
        q.star_breakdown      = feedback.scores.star_breakdown
        q.keywords_used       = {"keywords": feedback.scores.keywords_used}
        q.keywords_missed     = {"keywords": feedback.scores.keywords_missed}
        q.time_taken_seconds  = time_taken_seconds
        q.answered_at         = datetime.utcnow()

        session.questions_asked     += 1
        session.tokens_consumed     += feedback.tokens_consumed

        self._db.flush()

        # Check if all answered
        all_answered = session.questions_asked >= session.total_questions

        return {
            "session_id":      session_id,
            "question_number": question_number,
            "evaluation": {
                "scores": {
                    "overall":       feedback.scores.overall_score,
                    "confidence":    feedback.scores.confidence_score,
                    "technical":     feedback.scores.technical_score,
                    "communication": feedback.scores.communication_score,
                    "relevance":     feedback.scores.relevance_score,
                    "completeness":  feedback.scores.completeness_score,
                },
                "star_breakdown":  feedback.scores.star_breakdown,
                "keywords_used":   feedback.scores.keywords_used,
                "keywords_missed": feedback.scores.keywords_missed,
                "has_metrics":     feedback.scores.has_metrics,
                "word_count":      feedback.scores.word_count,
                **{k: v for k, v in feedback.qualitative.items()},
            },
            "model_answer":      feedback.model_answer,
            "improved_answer":   feedback.improved_answer,
            "session_complete":  all_answered,
            "progress":          {"answered": session.questions_asked,
                                  "total": session.total_questions},
            "next_action": "Call /complete for your full report" if all_answered
                           else f"Call /current-question for question {session.questions_asked + 1}",
        }

    # ── Complete Session ──────────────────────────────────────────────────────
    def complete_session(self, session_id: int, user_id: int) -> dict:
        session = self._get_session(session_id, user_id)

        if session.status == SessionStatus.COMPLETED:
            # Return existing report if already done
            existing = self._db.scalar(
                select(InterviewReport).where(
                    InterviewReport.session_id == session_id
                )
            )
            if existing:
                return _serialise_report(existing, session)

        answered_questions = [
            q for q in session.questions
            if q.user_answer is not None
        ]
        if not answered_questions:
            raise ValidationError("No answers submitted yet. Answer at least one question first.")

        # Compute averages
        avg = {
            "overall":       _avg([q.answer_score        or 0 for q in answered_questions]),
            "technical":     _avg([q.technical_score     or 0 for q in answered_questions]),
            "confidence":    _avg([q.confidence_score    or 0 for q in answered_questions]),
            "communication": _avg([q.communication_score or 0 for q in answered_questions]),
            "relevance":     _avg([q.relevance_score     or 0 for q in answered_questions]),
            "completeness":  _avg([q.relevance_score     or 0 for q in answered_questions]),
        }

        q_summaries = [
            {
                "question":       q.question_text,
                "type":           q.question_type.value,
                "score":          q.answer_score or 0,
                "answer_snippet": (q.user_answer or "")[:100],
            }
            for q in answered_questions
        ]

        with timed_agent_call(
            self._db, user_id=user_id, agent_name=AgentName.INTERVIEW_COACH,
            metadata={"session_id": session_id, "stage": "generate_report"},
        ) as ctx:
            report_data: SessionReport = generate_session_report(
                mode=session.mode.value,
                target_role=session.target_role,
                company=session.target_company,
                questions=q_summaries,
                avg_scores=avg,
            )
            usage = get_last_call_usage()
            ctx["input_tokens"]  = usage.get("input_tokens")
            ctx["output_tokens"] = usage.get("output_tokens")

        report = InterviewReport(
            session_id=session_id,
            user_id=user_id,
            overall_score=report_data.overall_score,
            technical_score=report_data.technical_score,
            confidence_score=report_data.confidence_score,
            communication_score=report_data.communication_score,
            relevance_score=report_data.relevance_score,
            completeness_score=report_data.completeness_score,
            grade=report_data.grade,
            verdict=report_data.verdict,
            executive_summary=report_data.executive_summary,
            strengths={"items": report_data.strengths},
            weaknesses={"items": report_data.weaknesses},
            improvement_tips={"tips": report_data.improvement_tips},
            per_question_summary={"questions": report_data.per_question_summary},
            model_used=settings.active_model,
            tokens_consumed=report_data.tokens_consumed,
            processing_time_ms=report_data.processing_time_ms,
        )
        self._db.add(report)

        session.status   = SessionStatus.COMPLETED
        session.ended_at = datetime.utcnow()
        self._db.flush()

        notify(
            self._db,
            user_id=user_id,
            type=NotificationType.INTERVIEW_EVALUATION_COMPLETED,
            title="Interview evaluation ready",
            message=f"You scored {report_data.overall_score:.0f}/100 ({report_data.grade}) on your mock interview.",
            action_url=f"/interview/sessions/{session_id}/report",
        )

        logger.info("session_completed", session_id=session_id,
                    overall_score=report_data.overall_score, grade=report_data.grade)
        return _serialise_report(report, session)

    # ── Abandon ───────────────────────────────────────────────────────────────
    def abandon_session(self, session_id: int, user_id: int) -> None:
        session = self._get_session(session_id, user_id)
        session.status   = SessionStatus.ABANDONED
        session.ended_at = datetime.utcnow()
        self._db.flush()

    # ── Queries ───────────────────────────────────────────────────────────────
    def get_session(self, session_id: int, user_id: int) -> InterviewSession:
        return self._get_session(session_id, user_id)

    def get_report(self, session_id: int, user_id: int) -> InterviewReport:
        self._get_session(session_id, user_id)   # ownership check
        r = self._db.scalar(
            select(InterviewReport).where(InterviewReport.session_id == session_id)
        )
        if not r:
            raise NotFoundError("InterviewReport for session", session_id)
        return r

    def list_sessions(self, user_id: int, limit: int = 20) -> list[InterviewSession]:
        # selectinload avoids an N+1 — without it, _session_list_item's
        # access to `s.report` per row issues one extra query per session
        # in the page (lazy-loaded relationship accessed in a loop).
        return list(self._db.scalars(
            select(InterviewSession)
            .options(selectinload(InterviewSession.report))
            .where(InterviewSession.user_id == user_id)
            .order_by(InterviewSession.started_at.desc())
            .limit(limit)
        ).all())

    # ── Internal ──────────────────────────────────────────────────────────────
    def _get_session(self, session_id: int, user_id: int) -> InterviewSession:
        s = self._db.scalar(
            select(InterviewSession).where(
                InterviewSession.session_id == session_id,
                InterviewSession.user_id    == user_id,
            )
        )
        if not s:
            raise NotFoundError("InterviewSession", session_id)
        return s


# ── Serialisers ───────────────────────────────────────────────────────────────
def _serialise_question(q: InterviewQuestion) -> dict:
    return {
        "question_id":     q.question_id,
        "question_number": q.question_number,
        "question_text":   q.question_text,
        "question_type":   q.question_type.value,
        "difficulty":      q.difficulty_level,
        "follow_up_hint":  q.follow_up_hint,
        "is_answered":     q.user_answer is not None,
    }


def _serialise_report(r: InterviewReport, s: InterviewSession) -> dict:
    return {
        "report_id":         r.report_id,
        "session_id":        s.session_id,
        "mode":              s.mode.value,
        "target_role":       s.target_role,
        "target_company":    s.target_company,
        "total_questions":   s.total_questions,
        "questions_answered": s.questions_asked,
        "scores": {
            "overall":       r.overall_score,
            "technical":     r.technical_score,
            "confidence":    r.confidence_score,
            "communication": r.communication_score,
            "relevance":     r.relevance_score,
            "completeness":  r.completeness_score,
            "grade":         r.grade,
        },
        "verdict":           r.verdict,
        "executive_summary": r.executive_summary,
        "strengths":         (r.strengths or {}).get("items", []),
        "weaknesses":        (r.weaknesses or {}).get("items", []),
        "improvement_tips":  (r.improvement_tips or {}).get("tips", []),
        "per_question_summary": (r.per_question_summary or {}).get("questions", []),
        "model_used":        r.model_used,
        "processing_time_ms": r.processing_time_ms,
        "created_at":        r.created_at,
    }


def _avg(values: list[float]) -> float:
    return round(sum(values) / max(1, len(values)), 2)
