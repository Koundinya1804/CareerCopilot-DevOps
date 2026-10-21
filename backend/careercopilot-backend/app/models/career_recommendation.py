"""
app/models/career_recommendation.py
─────────────────────────────────────
ORM model for career recommendation reports.
Stores the full multi-role recommendation output from the agent.
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


class RecommendationStatus(str, enum.Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    COMPLETE   = "complete"
    FAILED     = "failed"


class CareerRecommendationReport(Base):
    __tablename__ = "career_recommendation_reports"

    report_id:         Mapped[int]    = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:           Mapped[int]    = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    resume_id:         Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resumes.resume_id", ondelete="SET NULL"), nullable=True
    )

    # ── Inputs captured ────────────────────────────────────────────────────────
    input_skills:      Mapped[dict | None]  = mapped_column(JSON, nullable=True)
    input_interests:   Mapped[dict | None]  = mapped_column(JSON, nullable=True)
    input_experience_years: Mapped[float]   = mapped_column(Numeric(4, 1), nullable=False, default=0.0)
    input_education_level:  Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Top recommendation ─────────────────────────────────────────────────────
    top_recommended_role: Mapped[str | None]  = mapped_column(String(100), nullable=True)
    top_role_score:       Mapped[float]       = mapped_column(Numeric(5, 2), nullable=False, default=0.0)

    # ── Full output (JSON blobs) ───────────────────────────────────────────────
    recommended_roles:    Mapped[dict | None] = mapped_column(JSON, nullable=True)
    career_narrative:     Mapped[str | None]  = mapped_column(Text, nullable=True)
    personality_profile:  Mapped[dict | None] = mapped_column(JSON, nullable=True)
    industry_insights:    Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_plan:          Mapped[dict | None] = mapped_column(JSON, nullable=True)
    market_trends:        Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # ── Meta ───────────────────────────────────────────────────────────────────
    status:            Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus), nullable=False, default=RecommendationStatus.COMPLETE
    )
    model_used:        Mapped[str | None]  = mapped_column(String(100), nullable=True)
    tokens_consumed:   Mapped[int]         = mapped_column(Integer, nullable=False, default=0)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at:        Mapped[datetime]    = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user:   Mapped["User"]          = relationship("User")
    resume: Mapped["Resume | None"] = relationship("Resume")

    def __repr__(self) -> str:
        return (
            f"<CareerRecommendationReport id={self.report_id} "
            f"top_role={self.top_recommended_role} score={self.top_role_score}>"
        )
