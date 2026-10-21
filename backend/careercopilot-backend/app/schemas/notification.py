"""
app/schemas/notification.py
────────────────────────────
Pydantic v2 request / response schemas for the notification system.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.notification import NotificationPriority, NotificationType


# ── Read models ──────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    notification_id: int
    type:             NotificationType
    priority:         NotificationPriority
    title:            str
    message:          str
    icon:             str | None
    action_url:       str | None
    is_read:          bool
    read_at:          datetime | None
    created_at:       datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    total:            int
    unread_count:     int
    page:             int
    page_size:        int
    total_pages:      int
    notifications:    list[NotificationOut]


class UnreadCountResponse(BaseModel):
    unread_count: int


# ── Write models ─────────────────────────────────────────────────────────────

class NotificationCreateRequest(BaseModel):
    """Used by admin-broadcast / system-alert endpoints."""
    user_id:    int
    type:       NotificationType
    title:      str            = Field(..., min_length=1, max_length=255)
    message:    str            = Field(..., min_length=1)
    priority:   NotificationPriority = NotificationPriority.NORMAL
    icon:       str | None     = None
    action_url: str | None     = None


class BulkMarkReadResponse(BaseModel):
    marked_read: int
