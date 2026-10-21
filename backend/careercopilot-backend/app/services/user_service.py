"""
app/services/user_service.py
────────────────────────────
Business logic for user registration, authentication, and profile management.
All database interaction is isolated here; routes stay thin.

New in this version:
  - promote_to_admin()   — grant admin role to a user
  - demote_to_user()     — strip admin role
  - delete_user()        — hard delete (admin only)
  - reset_password()     — force password reset (admin only)
  - get_activity()       — recent agent logs for a user
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.user import User, UserProfile, UserRole, UserSkill, UserStatus
from app.schemas.user import (
    SkillAddRequest,
    UserProfileRequest,
    UserRegisterRequest,
)

logger = get_logger(__name__)


class UserService:
    """Encapsulates all user-related business operations."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Registration ──────────────────────────────────────────────────────────
    def register(self, payload: UserRegisterRequest) -> User:
        """
        Create a new user account.
        Raises ConflictError if email already exists.
        """
        existing = self._db.scalar(
            select(User).where(User.email == payload.email.lower())
        )
        if existing:
            raise ConflictError("An account with this email address already exists.")

        user = User(
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            full_name=payload.full_name.strip(),
        )
        self._db.add(user)
        self._db.flush()

        # Auto-create empty profile
        profile = UserProfile(user_id=user.user_id)
        self._db.add(profile)

        logger.info("user_registered", user_id=user.user_id, email=user.email)
        return user

    # ── Authentication ────────────────────────────────────────────────────────
    def authenticate(self, email: str, password: str) -> User:
        """
        Verify credentials and return the User.
        Raises InvalidCredentialsError on failure.
        """
        user: User | None = self._db.scalar(
            select(User).where(User.email == email.lower())
        )
        if not user:
            raise InvalidCredentialsError()

        if not user.password_hash:
            raise InvalidCredentialsError()

        # Truncate password to 72 bytes (bcrypt hard limit)
        plain_truncated = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        if not verify_password(plain_truncated, user.password_hash):
            raise InvalidCredentialsError()

        if user.status != UserStatus.ACTIVE:
            raise InvalidCredentialsError()

        user.last_login_at = datetime.utcnow()
        self._db.flush()

        logger.info("user_authenticated", user_id=user.user_id)
        return user

    # ── Lookups ───────────────────────────────────────────────────────────────
    def get_by_id(self, user_id: int) -> User:
        user = self._db.scalar(select(User).where(User.user_id == user_id))
        if not user:
            raise NotFoundError("User", user_id)
        return user

    def get_by_email(self, email: str) -> User | None:
        return self._db.scalar(select(User).where(User.email == email.lower()))

    # ── Profile management ────────────────────────────────────────────────────
    def update_profile(self, user_id: int, payload: UserProfileRequest) -> User:
        user = self.get_by_id(user_id)
        if not user.profile:
            user.profile = UserProfile(user_id=user_id)
            self._db.add(user.profile)

        p = user.profile
        for field_name in [
            "target_role", "current_role", "years_experience",
            "location", "linkedin_url", "github_url", "bio",
            "preferred_industries",
        ]:
            val = getattr(payload, field_name, None)
            if val is not None:
                setattr(p, field_name, val)

        self._db.flush()
        return user

    def add_skill(self, user_id: int, payload: SkillAddRequest) -> UserSkill:
        user = self.get_by_id(user_id)
        skill = UserSkill(
            user_id=user_id,
            skill_name=payload.skill_name.strip(),
            proficiency=payload.proficiency,
            years_used=payload.years_used,
        )
        self._db.add(skill)
        self._db.flush()
        return skill

    def delete_skill(self, user_id: int, skill_id: int) -> None:
        skill = self._db.scalar(
            select(UserSkill).where(
                UserSkill.skill_id == skill_id,
                UserSkill.user_id  == user_id,
            )
        )
        if not skill:
            raise NotFoundError("Skill", skill_id)
        self._db.delete(skill)
        self._db.flush()

    # ── Admin — Role Management ────────────────────────────────────────────────

    def promote_to_admin(self, user_id: int, requesting_admin_id: int) -> User:
        """Promote a user to admin role. Only admins can call this."""
        if user_id == requesting_admin_id:
            raise ConflictError("Cannot change your own role.")

        user = self.get_by_id(user_id)
        if user.role == UserRole.ADMIN:
            raise ConflictError("User is already an admin.")

        user.role = UserRole.ADMIN
        self._db.flush()

        logger.info(
            "user_promoted_to_admin",
            target_user_id=user_id,
            by_admin_id=requesting_admin_id,
        )
        return user

    def demote_to_user(self, user_id: int, requesting_admin_id: int) -> User:
        """Strip admin role from a user. Admins cannot demote themselves."""
        if user_id == requesting_admin_id:
            raise ConflictError("Cannot demote yourself.")

        user = self.get_by_id(user_id)
        if user.role == UserRole.USER:
            raise ConflictError("User is already a regular user.")

        user.role = UserRole.USER
        self._db.flush()

        logger.info(
            "user_demoted_to_user",
            target_user_id=user_id,
            by_admin_id=requesting_admin_id,
        )
        return user

    def reset_password(
        self,
        user_id:             int,
        new_password:        str,
        requesting_admin_id: int,
    ) -> User:
        """Force-reset a user's password (admin operation)."""
        user = self.get_by_id(user_id)

        # Truncate password to 72 bytes (bcrypt hard limit)
        safe_pw = new_password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
        user.password_hash = hash_password(safe_pw)
        self._db.flush()

        logger.info(
            "admin_password_reset",
            target_user_id=user_id,
            by_admin_id=requesting_admin_id,
        )
        return user

    def delete_user(self, user_id: int, requesting_admin_id: int) -> None:
        """Hard delete a user account (admin only). Cannot delete self."""
        if user_id == requesting_admin_id:
            raise ConflictError("Admins cannot delete their own account.")

        user = self.get_by_id(user_id)
        self._db.delete(user)
        self._db.flush()

        logger.info(
            "user_deleted",
            target_user_id=user_id,
            by_admin_id=requesting_admin_id,
        )

    def soft_delete_user(self, user_id: int, requesting_admin_id: int) -> User:
        """Mark user as deleted without removing data."""
        if user_id == requesting_admin_id:
            raise ConflictError("Admins cannot delete their own account.")

        user = self.get_by_id(user_id)
        user.status = UserStatus.DELETED
        self._db.flush()

        logger.info(
            "user_soft_deleted",
            target_user_id=user_id,
            by_admin_id=requesting_admin_id,
        )
        return user

    # ── Admin — Activity history ───────────────────────────────────────────────

    def get_activity(self, user_id: int, limit: int = 20) -> list[dict]:
        """
        Return recent agent log entries for a user.
        Used by the admin user detail page.
        """
        try:
            from app.models.agent_log import AgentLog
            logs = self._db.scalars(
                select(AgentLog)
                .where(AgentLog.user_id == user_id)
                .order_by(desc(AgentLog.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "log_id":             log.log_id,
                    "agent_name":         log.agent_name.value if hasattr(log.agent_name, "value") else str(log.agent_name),
                    "status":             log.status.value     if hasattr(log.status, "value")     else str(log.status),
                    "latency_ms":         log.latency_ms,
                    "estimated_cost_usd": log.estimated_cost_usd,
                    "created_at":         log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]
        except Exception:
            return []
