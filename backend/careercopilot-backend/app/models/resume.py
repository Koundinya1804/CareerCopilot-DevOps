"""
app/models/resume.py
────────────────────
Full ORM models for resume storage and analysis results.
Tables: resumes, career_reports, skill_gap_reports
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger, DateTime, Enum, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, func,
)
from sqlalchemy.dialects.mysql import JSON, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


# ── Enums ─────────────────────────────────────────────────────────────────────
class ResumeStatus(str, enum.Enum):
    UPLOADED   = "uploaded"
    PROCESSING = "processing"
    ANALYSED   = "analysed"
    FAILED     = "failed"


class SeniorityMatch(str, enum.Enum):
    BELOW       = "below"
    MATCH       = "match"
    ABOVE       = "above"
    UNDETECTED  = "undetected"


# ── Resume ────────────────────────────────────────────────────────────────────
class Resume(Base):
    __tablename__ = "resumes"

    resume_id:       Mapped[int]          = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:         Mapped[int]          = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    filename:        Mapped[str]          = mapped_column(String(255), nullable=False)
    s3_key:          Mapped[str]          = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int]          = mapped_column(BigInteger, nullable=False, default=0)
    mime_type:       Mapped[str]          = mapped_column(String(100), nullable=False, default="application/pdf")
    status:          Mapped[ResumeStatus] = mapped_column(Enum(ResumeStatus), nullable=False, default=ResumeStatus.UPLOADED, index=True)
    is_primary:      Mapped[int]          = mapped_column(TINYINT, nullable=False, default=0)
    raw_text:        Mapped[str | None]   = mapped_column(Text, nullable=True)   # extracted text cache
    page_count:      Mapped[int | None]   = mapped_column(SmallInteger, nullable=True)
    created_at:      Mapped[datetime]     = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at:      Mapped[datetime]     = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    user:           Mapped["User"]                = relationship("User", back_populates="resumes")
    career_reports: Mapped[list["CareerReport"]]  = relationship("CareerReport", back_populates="resume", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Resume id={self.resume_id} user={self.user_id} status={self.status}>"


# ── Career Report (ATS Analysis Output) ──────────────────────────────────────
class CareerReport(Base):
    __tablename__ = "career_reports"

    report_id:          Mapped[int]              = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:            Mapped[int]              = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id:          Mapped[int]              = mapped_column(Integer, ForeignKey("resumes.resume_id", ondelete="CASCADE"), nullable=False, index=True)

    # Scores
    ats_score:          Mapped[float]            = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    formatting_score:   Mapped[float]            = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    content_score:      Mapped[float]            = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    keyword_score:      Mapped[float]            = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    experience_score:   Mapped[float]            = mapped_column(Numeric(5, 2), nullable=False, default=0.0)

    # Counts
    total_skills_found: Mapped[int]              = mapped_column(SmallInteger, nullable=False, default=0)
    skills_matched:     Mapped[int]              = mapped_column(SmallInteger, nullable=False, default=0)
    skills_missing:     Mapped[int]              = mapped_column(SmallInteger, nullable=False, default=0)

    # Structured JSON fields
    extracted_skills:   Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    extracted_projects: Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    extracted_certs:    Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    extracted_education:Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    extracted_experience:Mapped[dict | None]     = mapped_column(JSON, nullable=True)
    contact_info:       Mapped[dict | None]      = mapped_column(JSON, nullable=True)

    # Analysis text
    summary:            Mapped[str | None]       = mapped_column(Text, nullable=True)
    strengths:          Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    improvements:       Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    keywords_found:     Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    keywords_missing:   Mapped[dict | None]      = mapped_column(JSON, nullable=True)
    seniority_match:    Mapped[SeniorityMatch]   = mapped_column(Enum(SeniorityMatch), nullable=False, default=SeniorityMatch.UNDETECTED)

    # Meta
    model_used:         Mapped[str | None]       = mapped_column(String(100), nullable=True)
    tokens_consumed:    Mapped[int]              = mapped_column(Integer, nullable=False, default=0)
    processing_time_ms: Mapped[int | None]       = mapped_column(Integer, nullable=True)
    created_at:         Mapped[datetime]         = mapped_column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    resume: Mapped["Resume"] = relationship("Resume", back_populates="career_reports")

    def __repr__(self) -> str:
        return f"<CareerReport id={self.report_id} ats={self.ats_score}>"
