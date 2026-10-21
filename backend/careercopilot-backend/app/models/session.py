"""
app/models/session.py  —  ChatSession & ChatMessage ORM model stubs
"""
from __future__ import annotations
import enum
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
if TYPE_CHECKING:
    from app.models.user import User

class AgentType(str, enum.Enum):
    RESUME       = "resume"
    INTERVIEW    = "interview"
    ROADMAP      = "roadmap"
    JOB_MATCH    = "job_match"
    COVER_LETTER = "cover_letter"
    QA_BOT       = "qa_bot"
    GENERAL      = "general"

class MessageRole(str, enum.Enum):
    USER      = "user"
    ASSISTANT = "assistant"
    SYSTEM    = "system"

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    chat_session_id: Mapped[int]       = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id:         Mapped[int]       = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    title:           Mapped[str|None]  = mapped_column(String(255), nullable=True)
    agent_type:      Mapped[AgentType] = mapped_column(Enum(AgentType), nullable=False, default=AgentType.GENERAL, index=True)
    total_messages:  Mapped[int]       = mapped_column(Integer, nullable=False, default=0)
    total_tokens_used: Mapped[int]     = mapped_column(Integer, nullable=False, default=0)
    created_at:      Mapped[datetime]  = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_message_at: Mapped[datetime]  = mapped_column(DateTime, nullable=False, server_default=func.now())
    user:     Mapped["User"]           = relationship("User", back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    message_id:      Mapped[int]         = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_session_id: Mapped[int]         = mapped_column(Integer, ForeignKey("chat_sessions.chat_session_id", ondelete="CASCADE"), nullable=False, index=True)
    role:            Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False, default=MessageRole.USER)
    content:         Mapped[str]         = mapped_column(Text, nullable=False)
    citations:       Mapped[dict|None]   = mapped_column(JSON, nullable=True)
    model_used:      Mapped[str|None]    = mapped_column(String(100), nullable=True)
    tokens_used:     Mapped[int]         = mapped_column(Integer, nullable=False, default=0)
    latency_ms:      Mapped[int|None]    = mapped_column(Integer, nullable=True)
    created_at:      Mapped[datetime]    = mapped_column(DateTime, nullable=False, server_default=func.now())
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
