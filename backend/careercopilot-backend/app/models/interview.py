"""
app/models/interview.py
────────────────────────
ORM models for the Interview Coach Agent.

Tables:
  interview_sessions   — one mock interview session per request
  interview_questions  — questions generated within a session
  interview_reports    — final aggregated performance report
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime, Enum, Float, ForeignKey, Integer,
    SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


# ── Enums ─────────────────────────────────────────────────────────────────────
class InterviewMode(str, enum.Enum):
    HR                  = "hr"
    TECHNICAL           = "technical"
    COMPANY_SPECIFIC    = "company_specific"


class InterviewDifficulty(str, enum.Enum):
    EASY   = "easy"
    MEDIUM = "medium"
    HARD   = "hard"


class SessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    ABANDONED   = "abandoned"


class QuestionType(str, enum.Enum):
    BEHAVIOURAL   = "behavioural"
    TECHNICAL     = "technical"
    SITUATIONAL   = "situational"
    SYSTEM_DESIGN = "system_design"
    CODING        = "coding"
    HR            = "hr"
    CULTURE_FIT   = "culture_fit"


# ── InterviewSession ──────────────────────────────────────────────────────────
class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    session_id:        Mapped[int]               = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:           Mapped[int]               = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id:         Mapped[int | None]        = mapped_column(Integer, ForeignKey("resumes.resume_id", ondelete="SET NULL"), nullable=True)

    # Config
    mode:              Mapped[InterviewMode]      = mapped_column(Enum(InterviewMode),       nullable=False, default=InterviewMode.HR)
    difficulty:        Mapped[InterviewDifficulty]= mapped_column(Enum(InterviewDifficulty), nullable=False, default=InterviewDifficulty.MEDIUM)
    target_role:       Mapped[str | None]        = mapped_column(String(150), nullable=True)
    target_company:    Mapped[str | None]        = mapped_column(String(150), nullable=True)
    total_questions:   Mapped[int]               = mapped_column(SmallInteger, nullable=False, default=5)
    questions_asked:   Mapped[int]               = mapped_column(SmallInteger, nullable=False, default=0)

    # Status
    status:            Mapped[SessionStatus]     = mapped_column(Enum(SessionStatus), nullable=False, default=SessionStatus.IN_PROGRESS, index=True)

    # Meta
    model_used:        Mapped[str | None]        = mapped_column(String(100), nullable=True)
    tokens_consumed:   Mapped[int]               = mapped_column(Integer, nullable=False, default=0)
    started_at:        Mapped[datetime]          = mapped_column(DateTime, nullable=False, server_default=func.now())
    ended_at:          Mapped[datetime | None]   = mapped_column(DateTime, nullable=True)

    # Relationships
    user:      Mapped["User"]                   = relationship("User")
    questions: Mapped[list["InterviewQuestion"]] = relationship("InterviewQuestion", back_populates="session", cascade="all, delete-orphan", order_by="InterviewQuestion.question_number")
    report:    Mapped["InterviewReport | None"]  = relationship("InterviewReport",   back_populates="session", uselist=False, cascade="all, delete-orphan")


# ── InterviewQuestion ─────────────────────────────────────────────────────────
class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    question_id:       Mapped[int]               = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id:        Mapped[int]               = mapped_column(Integer, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    question_number:   Mapped[int]               = mapped_column(SmallInteger, nullable=False)
    question_text:     Mapped[str]               = mapped_column(Text, nullable=False)
    question_type:     Mapped[QuestionType]      = mapped_column(Enum(QuestionType), nullable=False, default=QuestionType.HR)
    follow_up_hint:    Mapped[str | None]        = mapped_column(Text, nullable=True)
    difficulty_level:  Mapped[str | None]        = mapped_column(String(20), nullable=True)

    # Answer & evaluation
    user_answer:       Mapped[str | None]        = mapped_column(Text, nullable=True)
    answer_score:      Mapped[float | None]      = mapped_column(Float, nullable=True)
    confidence_score:  Mapped[float | None]      = mapped_column(Float, nullable=True)
    technical_score:   Mapped[float | None]      = mapped_column(Float, nullable=True)
    communication_score: Mapped[float | None]    = mapped_column(Float, nullable=True)
    relevance_score:   Mapped[float | None]      = mapped_column(Float, nullable=True)

    # Feedback
    feedback_json:     Mapped[dict | None]       = mapped_column(JSON, nullable=True)
    model_answer:      Mapped[str | None]        = mapped_column(Text, nullable=True)
    star_breakdown:    Mapped[dict | None]       = mapped_column(JSON, nullable=True)
    keywords_used:     Mapped[dict | None]       = mapped_column(JSON, nullable=True)
    keywords_missed:   Mapped[dict | None]       = mapped_column(JSON, nullable=True)

    # Timing
    time_taken_seconds: Mapped[int | None]       = mapped_column(Integer, nullable=True)
    answered_at:        Mapped[datetime | None]  = mapped_column(DateTime, nullable=True)

    # Relationships
    session: Mapped["InterviewSession"] = relationship("InterviewSession", back_populates="questions")


# ── InterviewReport ───────────────────────────────────────────────────────────
class InterviewReport(Base):
    __tablename__ = "interview_reports"

    report_id:         Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id:        Mapped[int]              = mapped_column(Integer, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id:           Mapped[int]              = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)

    # Overall scores (0–100)
    overall_score:         Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    technical_score:       Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_score:      Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    communication_score:   Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    relevance_score:       Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completeness_score:    Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Grade
    grade:            Mapped[str | None] = mapped_column(String(2), nullable=True)
    verdict:          Mapped[str | None] = mapped_column(String(100), nullable=True)

    # AI feedback
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths:         Mapped[dict | None] = mapped_column(JSON, nullable=True)
    weaknesses:        Mapped[dict | None] = mapped_column(JSON, nullable=True)
    improvement_tips:  Mapped[dict | None] = mapped_column(JSON, nullable=True)
    per_question_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Meta
    model_used:        Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_consumed:   Mapped[int]        = mapped_column(Integer, nullable=False, default=0)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at:        Mapped[datetime]   = mapped_column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    session: Mapped["InterviewSession"] = relationship("InterviewSession", back_populates="report")
