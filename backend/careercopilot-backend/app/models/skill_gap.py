"""
app/models/skill_gap.py
────────────────────────
ORM model for skill gap analysis reports.
Links user + optional resume → target_role → structured gap analysis.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.resume import Resume


class GapSeverity(str, enum.Enum):
    NONE     = "none"      # 90–100% match — ready to apply
    MINOR    = "minor"     # 70–89%  — 1–3 months prep
    MODERATE = "moderate"  # 50–69%  — 3–6 months prep
    MAJOR    = "major"     # 25–49%  — 6–12 months prep
    CRITICAL = "critical"  # <25%    — fundamental reskilling needed


class SkillGapReport(Base):
    __tablename__ = "skill_gap_reports"

    # ── Primary key ────────────────────────────────────────────────────────────
    gap_report_id:    Mapped[int]         = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Foreign keys ───────────────────────────────────────────────────────────
    user_id:          Mapped[int]         = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id:        Mapped[int | None]  = mapped_column(
        Integer, ForeignKey("resumes.resume_id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Role info ──────────────────────────────────────────────────────────────
    target_role_key:  Mapped[str]         = mapped_column(String(80),  nullable=False, index=True)
    target_role_title:Mapped[str]         = mapped_column(String(150), nullable=False)
    target_company:   Mapped[str | None]  = mapped_column(String(150), nullable=True)

    # ── Scores ─────────────────────────────────────────────────────────────────
    overall_match_pct:     Mapped[float]  = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    required_match_pct:    Mapped[float]  = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    preferred_match_pct:   Mapped[float]  = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    gap_severity:          Mapped[GapSeverity] = mapped_column(
        Enum(GapSeverity), nullable=False, default=GapSeverity.MAJOR, index=True
    )

    # ── Skill lists (JSON) ─────────────────────────────────────────────────────
    matched_skills:        Mapped[dict | None] = mapped_column(JSON, nullable=True)
    missing_required:      Mapped[dict | None] = mapped_column(JSON, nullable=True)
    missing_preferred:     Mapped[dict | None] = mapped_column(JSON, nullable=True)
    partially_matched:     Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Learning plan (JSON) ───────────────────────────────────────────────────
    learning_priorities:   Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_courses:   Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_projects:  Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_certs:     Mapped[dict | None] = mapped_column(JSON, nullable=True)
    estimated_prep_months: Mapped[int | None]  = mapped_column(Integer, nullable=True)

    # ── AI analysis text ───────────────────────────────────────────────────────
    executive_summary:     Mapped[str | None]  = mapped_column(Text, nullable=True)
    detailed_feedback:     Mapped[str | None]  = mapped_column(Text, nullable=True)
    quick_wins:            Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strengths:             Mapped[dict | None] = mapped_column(JSON, nullable=True)
    salary_insight:        Mapped[str | None]  = mapped_column(Text, nullable=True)

    # ── Meta ───────────────────────────────────────────────────────────────────
    model_used:            Mapped[str | None]  = mapped_column(String(100), nullable=True)
    tokens_consumed:       Mapped[int]         = mapped_column(Integer, nullable=False, default=0)
    processing_time_ms:    Mapped[int | None]  = mapped_column(Integer, nullable=True)
    created_at:            Mapped[datetime]    = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user:   Mapped["User"]           = relationship("User")
    resume: Mapped["Resume | None"]  = relationship("Resume")

    def __repr__(self) -> str:
        return (
            f"<SkillGapReport id={self.gap_report_id} "
            f"role={self.target_role_key} match={self.overall_match_pct}%>"
        )
