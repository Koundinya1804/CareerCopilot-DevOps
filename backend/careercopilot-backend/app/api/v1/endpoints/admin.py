"""
app/api/v1/endpoints/admin.py
──────────────────────────────
Admin Panel REST API — all routes require the `admin` role.

Endpoints:
  GET  /admin/overview                  — system-wide stats snapshot
  GET  /admin/users                     — paginated + searchable user list
  GET  /admin/users/{user_id}           — single user detail + usage stats
  PATCH /admin/users/{user_id}/status   — suspend or reactivate a user

  GET  /admin/agent-usage/summary       — aggregate agent analytics
  GET  /admin/agent-usage/by-agent      — per-agent-type breakdown
  GET  /admin/agent-usage/daily         — daily call volume (last N days)
  GET  /admin/agent-usage/weekly        — weekly call volume (last N weeks)
  GET  /admin/agent-usage/monthly       — monthly call volume (last N months)
  GET  /admin/agent-usage/top-users     — top N users by call volume
  GET  /admin/agent-usage/logs          — paginated raw agent log entries

  GET  /admin/documents                 — ChromaDB document counts per category
  GET  /admin/documents/most-uploaded   — KB categories ranked by document count
  GET  /admin/embedding-status          — ChromaDB connectivity health check

All routes are mounted under the /api/v1 prefix via router.py.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.dependencies import AdminUser, DBSession
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.agent_log import AgentLog
from app.models.user import User, UserStatus
from app.rag.kb_categories import KB_CATEGORIES
from app.rag.vectorstore.chroma_store import get_vectorstore
from app.schemas.user import APIResponse, MeResponse, UserRegisterResponse
from app.services.agent_log_service import AgentAnalyticsService

router = APIRouter(prefix="/admin", tags=["Admin Panel"])
logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. System Overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/overview",
    response_model=APIResponse,
    summary="[Admin] System-wide stats snapshot",
)
def get_overview(
    _:  AdminUser,
    db: DBSession,
) -> APIResponse:
    """
    Returns a high-level snapshot of the platform:
    user counts, agent call totals, KB document counts, and estimated cost.
    """
    # ── User stats ────────────────────────────────────────────────────────────
    total_users = db.scalar(select(func.count(User.user_id))) or 0
    active_users = (
        db.scalar(
            select(func.count(User.user_id)).where(
                User.status == UserStatus.ACTIVE
            )
        )
        or 0
    )
    suspended_users = (
        db.scalar(
            select(func.count(User.user_id)).where(
                User.status == UserStatus.SUSPENDED
            )
        )
        or 0
    )

    # ── Agent call stats ──────────────────────────────────────────────────────
    svc = AgentAnalyticsService(db)
    agent_summary = svc.get_summary()

    # ── KB stats ──────────────────────────────────────────────────────────────
    total_kb_docs = 0
    try:
        vs = get_vectorstore()
        all_stats = vs.get_all_stats()
        total_kb_docs = sum(s.get("count", 0) for s in all_stats)
    except Exception as exc:
        logger.warning("chroma_stats_unavailable", error=str(exc))

    return APIResponse(
        data={
            "users": {
                "total":     total_users,
                "active":    active_users,
                "suspended": suspended_users,
            },
            "agent_calls": {
                "total":        agent_summary["total_calls"],
                "successful":   agent_summary["successful_calls"],
                "failed":       agent_summary["failed_calls"],
                "success_rate": agent_summary["success_rate"],
            },
            "knowledge_base": {
                "total_documents":  total_kb_docs,
                "total_categories": len(KB_CATEGORIES),
            },
            "cost": {
                "total_estimated_usd": agent_summary["total_cost_usd"],
            },
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. User Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=APIResponse,
    summary="[Admin] Paginated, searchable user list",
)
def list_users(
    _:       AdminUser,
    db:      DBSession,
    page:    int           = Query(1,  ge=1),
    size:    int           = Query(20, ge=1, le=100),
    search:  Optional[str] = Query(None, description="Filter by email or full_name"),
) -> APIResponse:
    """Return paginated user list. Optional `search` filters by email or full name."""
    query = select(User)

    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            User.email.ilike(pattern) | User.full_name.ilike(pattern)
        )

    total  = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    users  = db.scalars(
        query.order_by(User.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return APIResponse(
        data={
            "total": total,
            "page":  page,
            "size":  size,
            "pages": max(1, (total + size - 1) // size),
            "items": [
                {
                    "user_id":    u.user_id,
                    "email":      u.email,
                    "full_name":  u.full_name,
                    "role":       u.role.value,
                    "status":     u.status.value,
                    "is_active":  u.is_active,
                    "created_at": u.created_at.isoformat() if u.created_at else None,
                }
                for u in users
            ],
        }
    )


@router.get(
    "/users/{user_id}",
    response_model=APIResponse,
    summary="[Admin] Get user detail with usage stats",
)
def get_user_detail(
    user_id: int,
    _:       AdminUser,
    db:      DBSession,
) -> APIResponse:
    """Return full user profile plus per-agent usage breakdown."""
    user = db.scalar(select(User).where(User.user_id == user_id))
    if not user:
        raise NotFoundError("User", user_id)

    # Usage stats for this user
    total_calls = (
        db.scalar(
            select(func.count(AgentLog.log_id)).where(
                AgentLog.user_id == user_id
            )
        )
        or 0
    )
    total_cost = (
        db.scalar(
            select(func.sum(AgentLog.estimated_cost_usd)).where(
                AgentLog.user_id == user_id,
                AgentLog.estimated_cost_usd.isnot(None),
            )
        )
        or 0.0
    )

    # Per-agent breakdown
    agent_rows = db.execute(
        select(
            AgentLog.agent_name,
            func.count(AgentLog.log_id).label("cnt"),
        )
        .where(AgentLog.user_id == user_id)
        .group_by(AgentLog.agent_name)
    ).all()

    return APIResponse(
        data={
            "user": {
                "user_id":    user.user_id,
                "email":      user.email,
                "full_name":  user.full_name,
                "role":       user.role.value,
                "status":     user.status.value,
                "is_active":  user.is_active,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
            "usage": {
                "total_calls":       total_calls,
                "estimated_cost_usd": round(float(total_cost), 4),
                "by_agent": {
                    row.agent_name.value: row.cnt for row in agent_rows
                },
            },
        }
    )


@router.patch(
    "/users/{user_id}/status",
    response_model=APIResponse,
    summary="[Admin] Suspend or reactivate a user",
)
def update_user_status(
    user_id:   int,
    is_active: bool,
    admin:     AdminUser,
    db:        DBSession,
) -> APIResponse:
    """
    Set `is_active=true` to reactivate a suspended user,
    `is_active=false` to suspend them.
    Admins cannot suspend themselves.
    """
    user = db.scalar(select(User).where(User.user_id == user_id))
    if not user:
        raise NotFoundError("User", user_id)

    if user.user_id == admin.user_id:
        from app.core.exceptions import ValidationError
        raise ValidationError("Admins cannot change their own account status.")

    user.status = UserStatus.ACTIVE if is_active else UserStatus.SUSPENDED
    db.commit()
    db.refresh(user)

    logger.info(
        "admin_user_status_updated",
        target_user_id=user_id,
        admin_id=admin.user_id,
        new_status=user.status.value,
    )

    return APIResponse(
        message=f"User {'activated' if is_active else 'suspended'} successfully.",
        data={
            "user_id":   user.user_id,
            "email":     user.email,
            "status":    user.status.value,
            "is_active": user.is_active,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Agent Usage Analytics
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/agent-usage/summary",
    response_model=APIResponse,
    summary="[Admin] System-wide agent usage summary",
)
def agent_usage_summary(
    _:  AdminUser,
    db: DBSession,
) -> APIResponse:
    return APIResponse(data=AgentAnalyticsService(db).get_summary())


@router.get(
    "/agent-usage/by-agent",
    response_model=APIResponse,
    summary="[Admin] Per-agent call breakdown",
)
def agent_usage_by_agent(
    _:  AdminUser,
    db: DBSession,
) -> APIResponse:
    return APIResponse(data=AgentAnalyticsService(db).get_by_agent())


@router.get(
    "/agent-usage/daily",
    response_model=APIResponse,
    summary="[Admin] Daily call volume",
)
def agent_usage_daily(
    _:    AdminUser,
    db:   DBSession,
    days: int = Query(30, ge=1, le=365, description="Number of past days to include"),
) -> APIResponse:
    return APIResponse(data=AgentAnalyticsService(db).get_daily_volume(days=days))


@router.get(
    "/agent-usage/weekly",
    response_model=APIResponse,
    summary="[Admin] Weekly call volume",
)
def agent_usage_weekly(
    _:     AdminUser,
    db:    DBSession,
    weeks: int = Query(12, ge=1, le=104, description="Number of past weeks to include"),
) -> APIResponse:
    return APIResponse(data=AgentAnalyticsService(db).get_weekly_volume(weeks=weeks))


@router.get(
    "/agent-usage/monthly",
    response_model=APIResponse,
    summary="[Admin] Monthly call volume",
)
def agent_usage_monthly(
    _:      AdminUser,
    db:     DBSession,
    months: int = Query(12, ge=1, le=36, description="Number of past months to include"),
) -> APIResponse:
    return APIResponse(data=AgentAnalyticsService(db).get_monthly_volume(months=months))


@router.get(
    "/agent-usage/top-users",
    response_model=APIResponse,
    summary="[Admin] Top users by agent call volume",
)
def agent_usage_top_users(
    _:     AdminUser,
    db:    DBSession,
    limit: int = Query(10, ge=1, le=50),
) -> APIResponse:
    return APIResponse(data=AgentAnalyticsService(db).get_top_users(limit=limit))


@router.get(
    "/agent-usage/logs",
    response_model=APIResponse,
    summary="[Admin] Paginated raw agent log entries",
)
def agent_usage_logs(
    _:          AdminUser,
    db:         DBSession,
    page:       int            = Query(1,  ge=1),
    page_size:  int            = Query(25, ge=1, le=100),
    agent_name: Optional[str]  = Query(None, description="Filter by agent name slug"),
    status:     Optional[str]  = Query(None, description="Filter by status: success | failed | timeout"),
) -> APIResponse:
    return APIResponse(
        data=AgentAnalyticsService(db).get_recent_logs(
            page=page,
            page_size=page_size,
            agent_name=agent_name,
            status=status,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/documents",
    response_model=APIResponse,
    summary="[Admin] ChromaDB document counts per KB category",
)
def get_documents(
    _: AdminUser,
) -> APIResponse:
    """
    Returns document count, collection name, and status for each KB category.
    A category with count=0 and status='empty' has not been ingested yet.
    """
    try:
        vs        = get_vectorstore()
        all_stats = vs.get_all_stats()
    except Exception as exc:
        logger.error("chroma_documents_error", error=str(exc))
        all_stats = [
            {"category": k, "collection": k, "count": 0, "status": "error"}
            for k in KB_CATEGORIES
        ]

    # Enrich with KB category metadata
    enriched = []
    total    = 0
    for stat in all_stats:
        cat_key  = stat["category"]
        cat_meta = KB_CATEGORIES.get(cat_key)
        enriched.append(
            {
                "category":    cat_key,
                "collection":  stat.get("collection", cat_key),
                "label":       cat_meta.label       if cat_meta else cat_key,
                "description": cat_meta.description if cat_meta else "",
                "icon":        cat_meta.icon        if cat_meta else "📁",
                "color":       cat_meta.color       if cat_meta else "#6366F1",
                "count":       stat.get("count", 0),
                "status":      stat.get("status", "unknown"),
            }
        )
        total += stat.get("count", 0)

    return APIResponse(
        data={
            "total_documents":  total,
            "total_categories": len(enriched),
            "categories":       enriched,
        }
    )


@router.get(
    "/documents/most-uploaded",
    response_model=APIResponse,
    summary="[Admin] KB categories ranked by distinct document count",
)
def most_uploaded_documents(_: AdminUser) -> APIResponse:
    """
    Ranks KB categories by number of distinct source documents (not chunks).
    Answers "which knowledge base areas get the most uploads".
    """
    try:
        vs = get_vectorstore()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ChromaDB unavailable: {exc}")

    ranked = []
    for cat_key, cat_meta in KB_CATEGORIES.items():
        try:
            store = vs.get_langchain_store(cat_key)
            result = store.get(include=["metadatas"])
            sources = {
                (m or {}).get("source") or (m or {}).get("filename")
                for m in (result.get("metadatas") or [])
                if m
            }
            doc_count = len({s for s in sources if s})
        except Exception:
            doc_count = 0
        ranked.append({
            "category": cat_key, "label": cat_meta.label,
            "document_count": doc_count,
        })

    ranked.sort(key=lambda r: r["document_count"], reverse=True)
    return APIResponse(data={"categories": ranked})


@router.get(
    "/embedding-status",
    response_model=APIResponse,
    summary="[Admin] ChromaDB connectivity and collection health",
)
def get_embedding_status(
    _: AdminUser,
) -> APIResponse:
    """
    Checks ChromaDB connectivity and returns per-collection health.
    healthy=True means at least one collection is reachable.
    """
    collections: list[dict] = []
    healthy     = False
    error_msg   = None

    try:
        vs        = get_vectorstore()
        all_stats = vs.get_all_stats()

        for stat in all_stats:
            ok = stat.get("status") == "ready"
            if ok:
                healthy = True
            collections.append(
                {
                    "category": stat["category"],
                    "count":    stat.get("count", 0),
                    "status":   stat.get("status", "unknown"),
                }
            )
    except Exception as exc:
        error_msg = str(exc)
        logger.error("embedding_status_error", error=error_msg)

    healthy_count = sum(1 for c in collections if c["status"] == "ready")

    return APIResponse(
        data={
            "healthy":             healthy,
            "healthy_collections": healthy_count,
            "total_collections":   len(collections),
            "collections":         collections,
            "error":               error_msg,
        }
    )
