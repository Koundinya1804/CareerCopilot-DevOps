"""
app/services/agent_log_service.py
──────────────────────────────────
Business logic for agent invocation logging and admin analytics.

Public API:
  log_call(db, ...)                  → AgentLog  (write path — called by agents)
  AgentAnalyticsService(db).*(...)   → dict       (read path — called by admin endpoints)

Cost estimates use the pricing for whichever model is actually configured as
DEFAULT_LLM_PROVIDER / DEFAULT_LLM_MODEL (Groq's llama-3.3-70b-versatile by
default — see app/core/config.py). Falls back to a small pricing table for
the other supported providers if the active model isn't recognised.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Generator

from sqlalchemy import func, select, desc, cast, Date
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.agent_log import AgentLog, AgentLogStatus, AgentName
from app.models.user import User

logger = get_logger(__name__)

# ── Cost constants (USD per 1M tokens, input/output) ──────────────────────────
# Groq pricing confirmed against Groq's published rates (July 2026). Other
# providers are listed for when DEFAULT_LLM_PROVIDER is switched away from Groq.
_PRICING_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # Groq
    "llama-3.3-70b-versatile":     (0.59, 0.79),
    "llama-3.1-8b-instant":        (0.05, 0.08),
    # Google Gemini
    "gemini-2.0-flash":            (0.075, 0.30),
    # Anthropic
    "claude-3-5-sonnet-20241022":  (3.00, 15.00),
    # OpenAI
    "gpt-4o-mini":                 (0.15, 0.60),
}
_FALLBACK_PRICING = (0.59, 0.79)  # Groq llama-3.3-70b-versatile — matches the app's actual default


def _active_pricing() -> tuple[float, float]:
    """(input_price_per_m, output_price_per_m) for whatever model is currently configured."""
    return _PRICING_PER_M_TOKENS.get(settings.active_model, _FALLBACK_PRICING)


# ── Cost helper ───────────────────────────────────────────────────────────────

def _estimate_cost(input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Return estimated USD cost; None if token counts are unavailable."""
    if input_tokens is None and output_tokens is None:
        return None
    i = input_tokens or 0
    o = output_tokens or 0
    input_price, output_price = _active_pricing()
    return round(
        (i / 1_000_000) * input_price
        + (o / 1_000_000) * output_price,
        6,
    )


# ── Write path ────────────────────────────────────────────────────────────────

def log_call(
    db: Session,
    *,
    user_id:        int,
    agent_name:     AgentName,
    status:         AgentLogStatus,
    latency_ms:     int | None           = None,
    input_tokens:   int | None           = None,
    output_tokens:  int | None           = None,
    error_message:  str | None           = None,
    extra_metadata: dict[str, Any] | None = None,
) -> AgentLog:
    """
    Persist a single agent invocation record.

    Call this from every agent service after completion (success or failure)::

        from app.services.agent_log_service import log_call
        from app.models.agent_log import AgentLogStatus, AgentName

        log_call(
            db,
            user_id=user.user_id,
            agent_name=AgentName.RESUME_ANALYSER,
            status=AgentLogStatus.SUCCESS,
            latency_ms=1240,
            input_tokens=2100,
            output_tokens=580,
        )
    """
    entry = AgentLog(
        user_id=user_id,
        agent_name=agent_name,
        status=status,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=_estimate_cost(input_tokens, output_tokens),
        error_message=error_message,
        extra_metadata=extra_metadata,
    )
    db.add(entry)
    db.flush()   # get log_id without waiting for the outer commit
    logger.info(
        "agent_call_logged",
        log_id=entry.log_id,
        agent=agent_name.value,
        status=status.value,
        latency_ms=latency_ms,
    )
    return entry


@contextmanager
def timed_agent_call(
    db: Session,
    *,
    user_id:    int,
    agent_name: AgentName,
    metadata:   dict[str, Any] | None = None,
) -> Generator[dict, None, None]:
    """
    Context-manager that automatically records latency and status::

        with timed_agent_call(db, user_id=uid, agent_name=AgentName.SKILL_GAP) as ctx:
            result = run_skill_gap_analysis(...)
            ctx["input_tokens"]  = result.input_tokens
            ctx["output_tokens"] = result.output_tokens

    On success the status is SUCCESS; any exception sets FAILED and re-raises.
    """
    ctx: dict[str, Any] = {
        "input_tokens":  None,
        "output_tokens": None,
        "error":         None,
    }
    start = time.monotonic()
    try:
        yield ctx
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log_call(
            db,
            user_id=user_id,
            agent_name=agent_name,
            status=AgentLogStatus.SUCCESS,
            latency_ms=elapsed_ms,
            input_tokens=ctx.get("input_tokens"),
            output_tokens=ctx.get("output_tokens"),
            extra_metadata=metadata,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        log_call(
            db,
            user_id=user_id,
            agent_name=agent_name,
            status=AgentLogStatus.FAILED,
            latency_ms=elapsed_ms,
            error_message=str(exc)[:1000],
            extra_metadata=metadata,
        )
        raise


# ── Read path (Admin analytics) ───────────────────────────────────────────────

class AgentAnalyticsService:
    """
    Read-only analytics service consumed by the Admin Panel endpoints.
    All methods return plain dicts — no Pydantic schemas needed.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """
        System-wide aggregate: total calls, success/fail counts, avg latency,
        total cost.
        """
        db = self._db

        total = db.scalar(select(func.count(AgentLog.log_id))) or 0

        successful = (
            db.scalar(
                select(func.count(AgentLog.log_id)).where(
                    AgentLog.status == AgentLogStatus.SUCCESS
                )
            )
            or 0
        )
        failed = (
            db.scalar(
                select(func.count(AgentLog.log_id)).where(
                    AgentLog.status == AgentLogStatus.FAILED
                )
            )
            or 0
        )

        avg_latency = (
            db.scalar(
                select(func.avg(AgentLog.latency_ms)).where(
                    AgentLog.latency_ms.isnot(None)
                )
            )
            or 0.0
        )

        total_cost = (
            db.scalar(
                select(func.sum(AgentLog.estimated_cost_usd)).where(
                    AgentLog.estimated_cost_usd.isnot(None)
                )
            )
            or 0.0
        )

        total_input_tokens = (
            db.scalar(select(func.sum(AgentLog.input_tokens))) or 0
        )
        total_output_tokens = (
            db.scalar(select(func.sum(AgentLog.output_tokens))) or 0
        )
        avg_input_tokens = (
            db.scalar(
                select(func.avg(AgentLog.input_tokens)).where(AgentLog.input_tokens.isnot(None))
            )
            or 0.0
        )
        avg_output_tokens = (
            db.scalar(
                select(func.avg(AgentLog.output_tokens)).where(AgentLog.output_tokens.isnot(None))
            )
            or 0.0
        )

        return {
            "total_calls":         total,
            "successful_calls":    successful,
            "failed_calls":        failed,
            "success_rate":        round(successful / total * 100, 1) if total else 0.0,
            "avg_latency_ms":      round(float(avg_latency), 1),
            "total_cost_usd":      round(float(total_cost), 4),
            "total_input_tokens":  int(total_input_tokens),
            "total_output_tokens": int(total_output_tokens),
            "total_tokens":        int(total_input_tokens) + int(total_output_tokens),
            "avg_input_tokens":    round(float(avg_input_tokens), 1),
            "avg_output_tokens":   round(float(avg_output_tokens), 1),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Per-agent breakdown
    # ─────────────────────────────────────────────────────────────────────────

    def get_by_agent(self) -> dict:
        """
        Break down calls, success rate, avg latency, and cost per AgentName.
        """
        db = self._db

        rows = db.execute(
            select(
                AgentLog.agent_name,
                func.count(AgentLog.log_id).label("total"),
                func.sum(
                    func.IF(AgentLog.status == AgentLogStatus.SUCCESS, 1, 0)
                ).label("successful"),
                func.avg(AgentLog.latency_ms).label("avg_latency"),
                func.sum(AgentLog.estimated_cost_usd).label("total_cost"),
            ).group_by(AgentLog.agent_name)
        ).all()

        result = []
        for row in rows:
            total      = row.total      or 0
            successful = int(row.successful or 0)
            result.append(
                {
                    "agent_name":       row.agent_name.value,
                    "total_calls":      total,
                    "successful_calls": successful,
                    "failed_calls":     total - successful,
                    "success_rate":     round(successful / total * 100, 1) if total else 0.0,
                    "avg_latency_ms":   round(float(row.avg_latency or 0), 1),
                    "total_cost_usd":   round(float(row.total_cost or 0), 4),
                }
            )

        return {"by_agent": sorted(result, key=lambda r: r["total_calls"], reverse=True)}

    # ─────────────────────────────────────────────────────────────────────────
    # Daily volume
    # ─────────────────────────────────────────────────────────────────────────

    def get_daily_volume(self, days: int = 30) -> dict:
        """
        Returns one row per calendar day for the last `days` days.
        """
        db    = self._db
        since = datetime.utcnow() - timedelta(days=days)

        rows = db.execute(
            select(
                cast(AgentLog.created_at, Date).label("date"),
                func.count(AgentLog.log_id).label("total"),
                func.sum(
                    func.IF(AgentLog.status == AgentLogStatus.SUCCESS, 1, 0)
                ).label("successful"),
                func.sum(
                    func.IF(AgentLog.status == AgentLogStatus.FAILED, 1, 0)
                ).label("failed"),
            )
            .where(AgentLog.created_at >= since)
            .group_by(cast(AgentLog.created_at, Date))
            .order_by(cast(AgentLog.created_at, Date))
        ).all()

        return {
            "days":  days,
            "daily": [
                {
                    "date":             str(row.date),
                    "total_calls":      row.total      or 0,
                    "successful_calls": int(row.successful or 0),
                    "failed_calls":     int(row.failed    or 0),
                }
                for row in rows
            ],
        }

    def get_weekly_volume(self, weeks: int = 12) -> dict:
        """Returns one row per ISO calendar week for the last `weeks` weeks."""
        db    = self._db
        since = datetime.utcnow() - timedelta(weeks=weeks)

        # MySQL YEARWEEK(date, 3) — mode 3 = ISO week numbering (Monday start,
        # week containing the year's first Thursday is week 1).
        week_expr = func.yearweek(AgentLog.created_at, 3)

        rows = db.execute(
            select(
                week_expr.label("yearweek"),
                func.min(cast(AgentLog.created_at, Date)).label("week_start"),
                func.count(AgentLog.log_id).label("total"),
                func.sum(func.IF(AgentLog.status == AgentLogStatus.SUCCESS, 1, 0)).label("successful"),
                func.sum(func.IF(AgentLog.status == AgentLogStatus.FAILED, 1, 0)).label("failed"),
            )
            .where(AgentLog.created_at >= since)
            .group_by(week_expr)
            .order_by(week_expr)
        ).all()

        return {
            "weeks": weeks,
            "weekly": [
                {
                    "week_start":       str(row.week_start),
                    "total_calls":      row.total      or 0,
                    "successful_calls": int(row.successful or 0),
                    "failed_calls":     int(row.failed    or 0),
                }
                for row in rows
            ],
        }

    def get_monthly_volume(self, months: int = 12) -> dict:
        """Returns one row per calendar month for the last `months` months."""
        db    = self._db
        since = datetime.utcnow() - timedelta(days=months * 31)

        month_expr = func.date_format(AgentLog.created_at, "%Y-%m")

        rows = db.execute(
            select(
                month_expr.label("month"),
                func.count(AgentLog.log_id).label("total"),
                func.sum(func.IF(AgentLog.status == AgentLogStatus.SUCCESS, 1, 0)).label("successful"),
                func.sum(func.IF(AgentLog.status == AgentLogStatus.FAILED, 1, 0)).label("failed"),
            )
            .where(AgentLog.created_at >= since)
            .group_by(month_expr)
            .order_by(month_expr)
        ).all()

        return {
            "months": months,
            "monthly": [
                {
                    "month":            row.month,
                    "total_calls":      row.total      or 0,
                    "successful_calls": int(row.successful or 0),
                    "failed_calls":     int(row.failed    or 0),
                }
                for row in rows
            ],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Top users by usage
    # ─────────────────────────────────────────────────────────────────────────

    def get_top_users(self, limit: int = 10) -> dict:
        """Return the top N users by total agent call volume."""
        db = self._db

        rows = db.execute(
            select(
                AgentLog.user_id,
                func.count(AgentLog.log_id).label("total_calls"),
                func.sum(AgentLog.estimated_cost_usd).label("total_cost"),
            )
            .group_by(AgentLog.user_id)
            .order_by(desc("total_calls"))
            .limit(limit)
        ).all()

        user_ids = [r.user_id for r in rows]
        if not user_ids:
            return {"top_users": []}

        user_map: dict[int, User] = {
            u.user_id: u
            for u in db.scalars(select(User).where(User.user_id.in_(user_ids))).all()
        }

        return {
            "top_users": [
                {
                    "user_id":       row.user_id,
                    "email":         user_map[row.user_id].email         if row.user_id in user_map else "unknown",
                    "full_name":     user_map[row.user_id].full_name     if row.user_id in user_map else "",
                    "total_calls":   row.total_calls   or 0,
                    "total_cost_usd": round(float(row.total_cost or 0), 4),
                }
                for row in rows
            ]
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Paginated raw logs
    # ─────────────────────────────────────────────────────────────────────────

    def get_recent_logs(
        self,
        page:       int             = 1,
        page_size:  int             = 25,
        agent_name: str | None      = None,
        status:     str | None      = None,
    ) -> dict:
        """
        Paginated, filterable agent log entries — newest first.
        """
        db    = self._db
        query = select(AgentLog)

        if agent_name:
            try:
                query = query.where(AgentLog.agent_name == AgentName(agent_name))
            except ValueError:
                pass  # ignore unknown enum — return unfiltered

        if status:
            try:
                query = query.where(AgentLog.status == AgentLogStatus(status))
            except ValueError:
                pass

        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        logs  = db.scalars(
            query.order_by(desc(AgentLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return {
            "total":       total,
            "page":        page,
            "page_size":   page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
            "logs": [
                {
                    "log_id":             log.log_id,
                    "user_id":            log.user_id,
                    "agent_name":         log.agent_name.value,
                    "status":             log.status.value,
                    "latency_ms":         log.latency_ms,
                    "input_tokens":       log.input_tokens,
                    "output_tokens":      log.output_tokens,
                    "estimated_cost_usd": log.estimated_cost_usd,
                    "error_message":      log.error_message,
                    "created_at":         log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
        }
