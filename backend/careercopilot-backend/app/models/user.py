"""
app/models/user.py
──────────────────
SQLAlchemy ORM model for the `users`, `user_profiles`, and `user_skills` tables.
Mirrors the MySQL schema defined in careercopilot_mysql_schema.sql.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import JSON, TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.resume import Resume
    from app.models.session import ChatSession
    from app.models.agent_log import AgentLog
    from app.models.notification import Notification

# ── Enums ─────────────────────────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    USER  = "user"
    ADMIN = "admin"
    GUEST = "guest"


class UserStatus(str, enum.Enum):
    ACTIVE    = "active"
    SUSPENDED = "suspended"
    DELETED   = "deleted"


class SkillProficiency(str, enum.Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    EXPERT       = "expert"


# ── User ──────────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    user_id:           Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    email:             Mapped[str]            = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash:     Mapped[str | None]     = mapped_column(String(255), nullable=True)
    full_name:         Mapped[str]            = mapped_column(String(150), nullable=False)
    role:              Mapped[UserRole]        = mapped_column(Enum(UserRole), nullable=False, default=UserRole.USER, index=True)
    oauth_provider:    Mapped[str | None]     = mapped_column(String(50),  nullable=True)
    oauth_sub:         Mapped[str | None]     = mapped_column(String(255), nullable=True)
    avatar_url:        Mapped[str | None]     = mapped_column(String(500), nullable=True)
    status:            Mapped[UserStatus]     = mapped_column(Enum(UserStatus), nullable=False, default=UserStatus.ACTIVE, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at:        Mapped[datetime]       = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at:        Mapped[datetime]       = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("oauth_provider", "oauth_sub", name="uq_users_oauth"),
    )

    # Relationships
    profile:            Mapped["UserProfile | None"]  = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    skills:             Mapped[list["UserSkill"]]     = relationship("UserSkill",   back_populates="user", cascade="all, delete-orphan")
    resumes:            Mapped[list["Resume"]]         = relationship("Resume",      back_populates="user", cascade="all, delete-orphan")
    chat_sessions:      Mapped[list["ChatSession"]]   = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    agent_logs: Mapped[list["AgentLog"]] = relationship(
    "AgentLog",
    back_populates="user",
    cascade="all, delete-orphan",
)
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="desc(Notification.created_at)",
    )
    # ── Helpers ───────────────────────────────────────────────────────────────
    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    def __repr__(self) -> str:
        return f"<User id={self.user_id} email={self.email} role={self.role}>"


# ── UserProfile ───────────────────────────────────────────────────────────────
class UserProfile(Base):
    __tablename__ = "user_profiles"

    profile_id:           Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:              Mapped[int]            = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=False)
    target_role:          Mapped[str | None]     = mapped_column(String(150), nullable=True, index=True)
    current_role:         Mapped[str | None]     = mapped_column(String(150), nullable=True)
    years_experience:     Mapped[int]            = mapped_column(TINYINT, nullable=False, default=0)
    location:             Mapped[str | None]     = mapped_column(String(150), nullable=True, index=True)
    linkedin_url:         Mapped[str | None]     = mapped_column(String(500), nullable=True)
    github_url:           Mapped[str | None]     = mapped_column(String(500), nullable=True)
    bio:                  Mapped[str | None]     = mapped_column(Text, nullable=True)
    preferred_industries: Mapped[dict | None]    = mapped_column(JSON, nullable=True)
    created_at:           Mapped[datetime]       = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at:           Mapped[datetime]       = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile user_id={self.user_id} target_role={self.target_role}>"


# ── UserSkill ─────────────────────────────────────────────────────────────────
class UserSkill(Base):
    __tablename__ = "user_skills"

    skill_id:   Mapped[int]             = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:    Mapped[int]             = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    skill_name: Mapped[str]             = mapped_column(String(100), nullable=False, index=True)
    proficiency: Mapped[SkillProficiency] = mapped_column(Enum(SkillProficiency), nullable=False, default=SkillProficiency.INTERMEDIATE)
    years_used: Mapped[int]             = mapped_column(TINYINT, nullable=False, default=0)
    created_at: Mapped[datetime]        = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "skill_name", name="uq_user_skill"),
    )

    user: Mapped["User"] = relationship("User", back_populates="skills")

    def __repr__(self) -> str:
        return f"<UserSkill user_id={self.user_id} skill={self.skill_name} level={self.proficiency}>"
