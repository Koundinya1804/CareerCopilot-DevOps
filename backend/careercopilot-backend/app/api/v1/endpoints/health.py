"""
app/api/v1/endpoints/health.py
──────────────────────────────
Liveness and readiness probes for Kubernetes / load balancer health checks.

  GET /api/v1/health         — liveness  (app is running)
  GET /api/v1/health/ready   — readiness (DB + Redis reachable)
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis import check_redis_connection
from app.db.session import engine

router  = APIRouter(tags=["Health"])
logger  = get_logger(__name__)


@router.get("/health", summary="Liveness probe")
def liveness() -> dict:
    return {
        "status":  "ok",
        "app":     settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env":     settings.APP_ENV,
    }


@router.get("/health/ready", summary="Readiness probe")
def readiness() -> dict:
    checks: dict[str, str] = {}

    # MySQL
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["mysql"] = "ok"
    except Exception as exc:
        logger.error("readiness_mysql_fail", error=str(exc))
        checks["mysql"] = "error"

    # Redis
    checks["redis"] = "ok" if check_redis_connection() else "error"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
