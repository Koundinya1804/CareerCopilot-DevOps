"""
app/models/agent_log.py
────────────────────────
ORM model for agent_logs table.

Tracks every invocation of any AI agent in the system so the Admin Panel
can display usage analytics, cost estimates, error rates, and per-user
consumption.

Table: agent_logs
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


# ── Enums ─────────────────────────────────────────────────────────────────────

class AgentName(str, enum.Enum):
    """Each agent that can be invoked through the platform."""
    RESUME_ANALYSER         = "resume_analyser"
    SKILL_GAP               = "skill_gap"
    CAREER_RECOMMENDATION   = "career_recommendation"
    INTERVIEW_COACH         = "interview_coach"
    RAG_CHAIN               = "rag_chain"
    SUPERVISOR              = "supervisor"
    UNKNOWN                 = "unknown"


class AgentLogStatus(str, enum.Enum):
    """Terminal state of the agent invocation."""
    SUCCESS = "success"
    FAILED  = "failed"
    TIMEOUT = "timeout"


# ── Model ─────────────────────────────────────────────────────────────────────

class AgentLog(Base):
    """
    One row per agent invocation.

    Populated by each service/agent via AgentLogService.log_call().
    The admin panel reads this table exclusively through AgentLogService.
    """
    __tablename__ = "agent_logs"

    # ── Primary key ────────────────────────────────────────────────────────────
    log_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ── Foreign key ────────────────────────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Agent identity ─────────────────────────────────────────────────────────
    agent_name: Mapped[AgentName] = mapped_column(
        Enum(AgentName),
        nullable=False,
        index=True,
        default=AgentName.UNKNOWN,
    )

    # ── Outcome ────────────────────────────────────────────────────────────────
    status: Mapped[AgentLogStatus] = mapped_column(
        Enum(AgentLogStatus),
        nullable=False,
        index=True,
        default=AgentLogStatus.SUCCESS,
    )

    # ── Performance ────────────────────────────────────────────────────────────
    latency_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Wall-clock time from request to response in ms"
    )

    # ── LLM token usage ────────────────────────────────────────────────────────
    input_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    output_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ── Cost estimate (Gemini 2.0 Flash pricing) ───────────────────────────────
    # $0.075 / 1M input tokens, $0.30 / 1M output tokens
    estimated_cost_usd: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Estimated USD cost at Gemini 2.0 Flash pricing"
    )

    # ── Error context ──────────────────────────────────────────────────────────
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ── Optional metadata (target_role, resume_id, session_id, etc.) ──────────
    extra_metadata: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    # ── Relationship ───────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="agent_logs")
