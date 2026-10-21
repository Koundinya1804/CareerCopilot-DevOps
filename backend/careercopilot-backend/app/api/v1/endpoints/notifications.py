"""
app/api/v1/endpoints/notifications.py
────────────────────────────────────────
Notification system REST API.

  GET    /api/v1/notifications                — paginated + searchable + filterable list
  GET    /api/v1/notifications/unread-count    — badge count for the bell icon
  PATCH  /api/v1/notifications/{id}/read       — mark one notification as read
  POST   /api/v1/notifications/mark-all-read   — mark every unread notification as read
  DELETE /api/v1/notifications/{id}            — delete a notification

All routes require authentication; a user can only ever see/mutate their own
notifications (enforced in NotificationService via user_id scoping).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DBSession
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.schemas.notification import (
    BulkMarkReadResponse,
    NotificationListResponse,
    NotificationOut,
    UnreadCountResponse,
)
from app.schemas.user import APIResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])
logger = get_logger(__name__)


def _svc(db: DBSession) -> NotificationService:
    return NotificationService(db)


# ─────────────────────────────────────────────────────────────────────────────
# List (paginated, searchable, filterable)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=APIResponse,
    summary="List the current user's notifications",
)
def list_notifications(
    user: CurrentUser,
    db:   DBSession,
    page:        int  = Query(1,  ge=1),
    page_size:   int  = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    type:        str | None = Query(None, description="Filter by NotificationType value"),
    search:      str | None = Query(None, description="Search title/message"),
) -> APIResponse:
    result = _svc(db).list_for_user(
        user.user_id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
        type_filter=type,
        search=search,
    )
    payload = NotificationListResponse(
        total=result["total"],
        unread_count=result["unread_count"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
        notifications=[NotificationOut.model_validate(n) for n in result["notifications"]],
    )
    return APIResponse(message="OK", data=payload)


@router.get(
    "/unread-count",
    response_model=APIResponse,
    summary="Unread notification count (for the bell badge)",
)
def unread_count(user: CurrentUser, db: DBSession) -> APIResponse:
    count = _svc(db).unread_count(user.user_id)
    return APIResponse(message="OK", data=UnreadCountResponse(unread_count=count))


# ─────────────────────────────────────────────────────────────────────────────
# Mutations
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/{notification_id}/read",
    response_model=APIResponse,
    summary="Mark one notification as read",
)
def mark_read(notification_id: int, user: CurrentUser, db: DBSession) -> APIResponse:
    notif = _svc(db).mark_read(user.user_id, notification_id)
    if notif is None:
        raise NotFoundError(resource="Notification", identifier=str(notification_id))
    return APIResponse(message="Marked as read", data=NotificationOut.model_validate(notif))


@router.post(
    "/mark-all-read",
    response_model=APIResponse,
    summary="Mark every unread notification as read",
)
def mark_all_read(user: CurrentUser, db: DBSession) -> APIResponse:
    marked = _svc(db).mark_all_read(user.user_id)
    return APIResponse(message="OK", data=BulkMarkReadResponse(marked_read=marked))


@router.delete(
    "/{notification_id}",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a notification",
)
def delete_notification(notification_id: int, user: CurrentUser, db: DBSession) -> APIResponse:
    deleted = _svc(db).delete(user.user_id, notification_id)
    if not deleted:
        raise NotFoundError(resource="Notification", identifier=str(notification_id))
    return APIResponse(message="Notification deleted", data=None)
