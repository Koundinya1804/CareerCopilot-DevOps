"""
app/langgraph/memory/memory_store.py
──────────────────────────────────────
Redis-backed conversation memory for the multi-agent graph.

Stores:
  - Full AgentState per session (TTL 24h)
  - Conversation history (messages list)
  - User context cache (skills, resume snippet, etc.)
  - A per-user index of recent session IDs, so "chat history" (list your
    past conversations) is actually possible — session state itself is
    keyed only by session_id, with no reverse index back to the user, so
    without this a user's own past sessions were unrecoverable unless the
    frontend happened to still have the session_id in memory.

Keys:
  langgraph:session:{session_id}:state    → full state JSON
  langgraph:session:{session_id}:messages → message list JSON
  langgraph:user:{user_id}:context        → user context cache (7d TTL)
  langgraph:user:{user_id}:sessions       → sorted set of session_ids,
                                             score = last-activity unix time
"""
from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_SESSION_TTL      = int(timedelta(hours=24).total_seconds())
_CONTEXT_TTL      = int(timedelta(days=7).total_seconds())
_SESSION_INDEX_TTL = int(timedelta(days=7).total_seconds())  # outlives individual sessions so the list doesn't vanish the moment a session's own TTL expires
_MAX_SESSIONS_PER_USER = 50


# ── Key builders ──────────────────────────────────────────────────────────────
def _state_key(session_id: str)     -> str: return f"langgraph:session:{session_id}:state"
def _msg_key(session_id: str)       -> str: return f"langgraph:session:{session_id}:messages"
def _context_key(user_id: int)      -> str: return f"langgraph:user:{user_id}:context"
def _user_sessions_key(user_id: int) -> str: return f"langgraph:user:{user_id}:sessions"


class GraphMemory:
    """
    Manages persistent memory for LangGraph sessions.
    Injected into the graph as a dependency — not a singleton,
    because each request may use a different Redis client.
    """

    def __init__(self, redis_client) -> None:  # type: ignore[type-arg]
        self._r = redis_client

    # ── Session state ─────────────────────────────────────────────────────────
    def save_state(self, session_id: str, state: dict) -> None:
        """Persist the full graph state after each node execution."""
        try:
            # Exclude non-serialisable or very large fields
            safe = {k: v for k, v in state.items() if k != "messages"}
            self._r.setex(_state_key(session_id), _SESSION_TTL, json.dumps(safe, default=str))
        except Exception as exc:
            logger.warning("memory_save_state_failed", session=session_id, error=str(exc))

    def load_state(self, session_id: str) -> dict | None:
        """Load previously saved graph state for session resumption."""
        try:
            raw = self._r.get(_state_key(session_id))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("memory_load_state_failed", session=session_id, error=str(exc))
            return None

    def delete_session(self, session_id: str) -> None:
        try:
            self._r.delete(_state_key(session_id), _msg_key(session_id))
        except Exception:
            pass

    # ── Messages ──────────────────────────────────────────────────────────────
    def append_messages(self, session_id: str, messages: list[dict]) -> None:
        """Append new messages to the session's message history."""
        try:
            existing = self.load_messages(session_id)
            merged   = existing + messages
            # Keep last 50 messages to bound memory
            merged   = merged[-50:]
            self._r.setex(_msg_key(session_id), _SESSION_TTL, json.dumps(merged, default=str))
        except Exception as exc:
            logger.warning("memory_append_messages_failed", error=str(exc))

    def load_messages(self, session_id: str) -> list[dict]:
        """Load conversation history for multi-turn context."""
        try:
            raw = self._r.get(_msg_key(session_id))
            return json.loads(raw) if raw else []
        except Exception:
            return []

    # ── User context cache ─────────────────────────────────────────────────────
    def save_user_context(self, user_id: int, context: dict) -> None:
        """Cache user profile data (skills, resume snippet, preferences)."""
        try:
            self._r.setex(_context_key(user_id), _CONTEXT_TTL, json.dumps(context, default=str))
        except Exception as exc:
            logger.warning("memory_save_context_failed", user_id=user_id, error=str(exc))

    def load_user_context(self, user_id: int) -> dict | None:
        """Load cached user context to pre-populate graph state."""
        try:
            raw = self._r.get(_context_key(user_id))
            return json.loads(raw) if raw else None
        except Exception:
            return None

    def update_user_context(self, user_id: int, **kwargs: Any) -> None:
        """Merge new fields into the existing user context cache."""
        existing = self.load_user_context(user_id) or {}
        existing.update({k: v for k, v in kwargs.items() if v is not None})
        self.save_user_context(user_id, existing)

    # ── Session listing ────────────────────────────────────────────────────────
    def session_exists(self, session_id: str) -> bool:
        try:
            return bool(self._r.exists(_state_key(session_id)))
        except Exception:
            return False

    def is_session_tracked(self, user_id: int, session_id: str) -> bool:
        """Cheap O(1) membership check — use this instead of
        list_user_sessions() when you only need to know whether a session
        is already in the user's history index, not fetch the whole list."""
        try:
            return self._r.zscore(_user_sessions_key(user_id), session_id) is not None
        except Exception:
            return False

    def get_session_ttl(self, session_id: str) -> int:
        """Returns remaining TTL in seconds, or -1 if not found."""
        try:
            return int(self._r.ttl(_state_key(session_id)))
        except Exception:
            return -1

    # ── Per-user session index (for "chat history") ────────────────────────────
    def track_user_session(self, user_id: int, session_id: str, preview: str | None = None) -> None:
        """
        Record that `session_id` belongs to `user_id` and was just active,
        for the "recent conversations" list. Call this every time a session
        is saved (i.e. from _save_session_result), not just on creation —
        the sorted-set score is last-activity time, so an old conversation
        that gets continued jumps back to the top of the list.

        `preview` (typically the first ~80 chars of the user's first
        message) is cached alongside so the history list can show something
        meaningful without loading full message history for every session.
        """
        try:
            now = time.time()
            self._r.zadd(_user_sessions_key(user_id), {session_id: now})
            self._r.expire(_user_sessions_key(user_id), _SESSION_INDEX_TTL)
            # Trim to the most recent N sessions so this can't grow forever
            self._r.zremrangebyrank(_user_sessions_key(user_id), 0, -(_MAX_SESSIONS_PER_USER + 1))
            if preview:
                self._r.setex(
                    f"langgraph:session:{session_id}:preview", _SESSION_INDEX_TTL, preview[:120]
                )
        except Exception as exc:
            logger.warning("memory_track_user_session_failed", user_id=user_id, error=str(exc))

    def list_user_sessions(self, user_id: int, limit: int = 20) -> list[dict]:
        """
        Returns the user's most recently active sessions, newest first:
        [{"session_id": ..., "last_active": <unix ts>, "preview": ..., "still_live": bool}, ...]

        `still_live` reflects whether the session's own state has expired
        (24h TTL) even though it still appears in the 7-day history index —
        a "dead" session can be shown greyed-out / as read-only in the UI
        rather than silently disappearing from history the moment it can no
        longer be resumed.
        """
        try:
            raw = self._r.zrevrange(_user_sessions_key(user_id), 0, limit - 1, withscores=True)
        except Exception as exc:
            logger.warning("memory_list_user_sessions_failed", user_id=user_id, error=str(exc))
            return []

        results = []
        for session_id, score in raw:
            sid = session_id if isinstance(session_id, str) else session_id.decode()
            preview = None
            try:
                preview = self._r.get(f"langgraph:session:{sid}:preview")
            except Exception:
                pass
            results.append({
                "session_id":  sid,
                "last_active": float(score),
                "preview":     preview,
                "still_live":  self.session_exists(sid),
            })
        return results
