"""
app/services/notification_service.py
──────────────────────────────────────
Business logic for the notification system.

Write path — called by AI service modules on job completion, or by admin /
auth flows for system & login alerts::

    from app.services.notification_service import notify

    notify(
        db,
        user_id=user_id,
        type=NotificationType.RESUME_ANALYSIS_COMPLETED,
        title="Resume analysis complete",
        message=f"Your resume '{resume.filename}' scored {ats_score}/100 ATS.",
        action_url=f"/resume/{resume.resume_id}/report",
    )

Read path — consumed by the notifications endpoints::

    svc = NotificationService(db)
    svc.list_for_user(user_id, page=1, page_size=20, unread_only=False)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.notification import (
    DEFAULT_ICON_BY_TYPE,
    Notification,
    NotificationPriority,
    NotificationType,
)

logger = get_logger(__name__)


# ── Write path ────────────────────────────────────────────────────────────────

def notify(
    db: Session,
    *,
    user_id:    int,
    type:       NotificationType,
    title:      str,
    message:    str,
    priority:   NotificationPriority = NotificationPriority.NORMAL,
    icon:       str | None           = None,
    action_url: str | None           = None,
) -> Notification:
    """
    Persist a single notification. Safe to call from within an existing
    request-scoped session/transaction — flushes but does not commit, so it
    rides along with the caller's outer commit (mirrors agent_log_service.log_call).

    Never raises into the caller's happy path: a failure here should not break
    the underlying job (resume analysis, etc.) that triggered it.
    """
    try:
        entry = Notification(
            user_id=user_id,
            type=type,
            priority=priority,
            title=title,
            message=message,
            icon=icon or DEFAULT_ICON_BY_TYPE.get(type),
            action_url=action_url,
        )
        db.add(entry)
        db.flush()
        logger.info(
            "notification_created",
            notification_id=entry.notification_id,
            user_id=user_id,
            type=type.value,
        )
        return entry
    except Exception:
        logger.exception("notification_create_failed", user_id=user_id, type=type.value)
        raise


# ── Read / management path ────────────────────────────────────────────────────

class NotificationService:
    """Read + mutate operations consumed by the notification endpoints."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def unread_count(self, user_id: int) -> int:
        return (
            self._db.scalar(
                select(func.count(Notification.notification_id)).where(
                    Notification.user_id == user_id,
                    Notification.is_read.is_(False),
                )
            )
            or 0
        )

    def list_for_user(
        self,
        user_id:      int,
        *,
        page:         int             = 1,
        page_size:    int             = 20,
        unread_only:  bool            = False,
        type_filter:  str | None      = None,
        search:       str | None      = None,
    ) -> dict[str, Any]:
        """Paginated, filterable, searchable notification list — newest first."""
        db = self._db
        query = select(Notification).where(Notification.user_id == user_id)

        if unread_only:
            query = query.where(Notification.is_read.is_(False))

        if type_filter:
            try:
                query = query.where(Notification.type == NotificationType(type_filter))
            except ValueError:
                pass  # unknown type filter — ignore, return unfiltered

        if search:
            like = f"%{search.strip()}%"
            query = query.where(
                or_(Notification.title.ilike(like), Notification.message.ilike(like))
            )

        total = db.scalar(select(func.count()).select_from(query.subquery())) or 0

        rows = db.scalars(
            query.order_by(desc(Notification.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return {
            "total":         total,
            "unread_count":  self.unread_count(user_id),
            "page":          page,
            "page_size":     page_size,
            "total_pages":   max(1, (total + page_size - 1) // page_size),
            "notifications": rows,
        }

    def mark_read(self, user_id: int, notification_id: int) -> Notification | None:
        notif = self._db.scalar(
            select(Notification).where(
                Notification.notification_id == notification_id,
                Notification.user_id == user_id,
            )
        )
        if notif is None:
            return None
        if not notif.is_read:
            notif.is_read = True
            notif.read_at = datetime.utcnow()
            self._db.flush()
        return notif

    def mark_all_read(self, user_id: int) -> int:
        rows = self._db.scalars(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        ).all()
        now = datetime.utcnow()
        for notif in rows:
            notif.is_read = True
            notif.read_at = now
        self._db.flush()
        return len(rows)

    def delete(self, user_id: int, notification_id: int) -> bool:
        notif = self._db.scalar(
            select(Notification).where(
                Notification.notification_id == notification_id,
                Notification.user_id == user_id,
            )
        )
        if notif is None:
            return False
        self._db.delete(notif)
        self._db.flush()
        return True
