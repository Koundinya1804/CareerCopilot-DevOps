"""
app/models/notification.py
───────────────────────────
ORM model for the `notifications` table.

Every notification surfaced in the bell dropdown / notification page is a row
here. Rows are written by NotificationService.create() — either called
directly by an endpoint (e.g. admin broadcasting a system alert) or by the
AI service layer when a long-running job (resume analysis, skill gap, career
recommendation, interview evaluation, KB indexing, ...) finishes.

Table: notifications
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


# ── Enums ─────────────────────────────────────────────────────────────────────

class NotificationType(str, enum.Enum):
    """Every kind of notification the platform can raise."""
    RESUME_ANALYSIS_COMPLETED       = "resume_analysis_completed"
    SKILL_GAP_REPORT_COMPLETED      = "skill_gap_report_completed"
    CAREER_RECOMMENDATION_COMPLETED = "career_recommendation_completed"
    INTERVIEW_EVALUATION_COMPLETED  = "interview_evaluation_completed"
    KB_INDEXING_COMPLETED           = "kb_indexing_completed"
    DOCUMENT_UPLOADED               = "document_uploaded"
    CHROMA_INDEXING_FINISHED        = "chroma_indexing_finished"
    SYSTEM_ALERT                    = "system_alert"
    ADMIN_ACTION                    = "admin_action"
    LOGIN_ALERT                     = "login_alert"
    ERROR_NOTIFICATION              = "error_notification"
    WEEKLY_PROGRESS_REMINDER        = "weekly_progress_reminder"
    LEARNING_ROADMAP_REMINDER       = "learning_roadmap_reminder"


class NotificationPriority(str, enum.Enum):
    LOW    = "low"
    NORMAL = "normal"
    HIGH   = "high"
    URGENT = "urgent"


# Default Lucide icon name per type — the frontend maps this string straight
# to a `lucide-react` component, so keep these in sync with NotificationBell.tsx.
DEFAULT_ICON_BY_TYPE: dict[NotificationType, str] = {
    NotificationType.RESUME_ANALYSIS_COMPLETED:       "FileText",
    NotificationType.SKILL_GAP_REPORT_COMPLETED:      "Target",
    NotificationType.CAREER_RECOMMENDATION_COMPLETED: "TrendingUp",
    NotificationType.INTERVIEW_EVALUATION_COMPLETED:  "Mic",
    NotificationType.KB_INDEXING_COMPLETED:           "Database",
    NotificationType.DOCUMENT_UPLOADED:                "Upload",
    NotificationType.CHROMA_INDEXING_FINISHED:        "Layers",
    NotificationType.SYSTEM_ALERT:                    "AlertTriangle",
    NotificationType.ADMIN_ACTION:                    "ShieldAlert",
    NotificationType.LOGIN_ALERT:                     "LogIn",
    NotificationType.ERROR_NOTIFICATION:              "AlertCircle",
    NotificationType.WEEKLY_PROGRESS_REMINDER:        "CalendarClock",
    NotificationType.LEARNING_ROADMAP_REMINDER:       "GraduationCap",
}


# ── Model ─────────────────────────────────────────────────────────────────────

class Notification(Base):
    """One row per notification delivered to a user."""
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType), nullable=False, index=True
    )

    priority: Mapped[NotificationPriority] = mapped_column(
        Enum(NotificationPriority), nullable=False, default=NotificationPriority.NORMAL
    )

    title:   Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Lucide icon name rendered in the bell dropdown / notification page.
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Frontend route the notification navigates to when clicked, e.g.
    # "/resume/42/report" or "/admin/logs".
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification id={self.notification_id} type={self.type.value} read={self.is_read}>"
