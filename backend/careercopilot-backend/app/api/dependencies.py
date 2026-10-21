"""
app/api/dependencies.py
────────────────────────
Reusable FastAPI dependencies injected via Depends().

  get_current_user()   — validates JWT, returns active User
  require_admin()      — like get_current_user but asserts admin role
  get_user_service()   — injects UserService with db session
  require_rate_limit() — per-user sliding-window rate limiter
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    InsufficientPermissionsError,
    RateLimitError,
    TokenInvalidError,
)
from app.core.logging import get_logger
from app.core.security import decode_token
from app.db.redis import TokenBlacklist, get_redis
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.user_service import UserService

logger = get_logger(__name__)

_bearer_scheme = HTTPBearer(auto_error=True)


# ── Core injection helpers ────────────────────────────────────────────────────
def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


# ── Authentication ────────────────────────────────────────────────────────────
def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    db:          Session  = Depends(get_db),
    redis:       Redis    = Depends(get_redis),  # type: ignore[type-arg]
) -> User:
    """
    Validate the Bearer JWT and return the corresponding User.

    Raises:
        TokenInvalidError          — missing, malformed, wrong type
        AuthenticationError        — token is revoked / user inactive
    """
    token = credentials.credentials

    try:
        payload = decode_token(token)
    except JWTError:
        raise TokenInvalidError()

    if payload.get("type") != "access":
        raise TokenInvalidError()

    # Check if token has been revoked (logout)
    jti = str(payload.get("jti", ""))
    if jti and TokenBlacklist(redis).is_revoked(jti):
        logger.warning("revoked_token_used", jti=jti)
        raise TokenInvalidError()

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise TokenInvalidError()

    svc = UserService(db)
    user = svc.get_by_id(int(user_id_str))
    return user


def get_current_user_optional(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
    db:  Session = Depends(get_db),
    redis: Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> User | None:
    """Like get_current_user but returns None for unauthenticated requests."""
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db, redis)
    except Exception:
        return None


# ── Authorisation ─────────────────────────────────────────────────────────────
def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the authenticated user has the admin role."""
    if current_user.role != UserRole.ADMIN:
        raise InsufficientPermissionsError(required_role="admin")
    return current_user


# ── Rate Limiting ─────────────────────────────────────────────────────────────
def require_rate_limit(
    current_user: User  = Depends(get_current_user),
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> User:
    """
    Sliding-window rate limit for authenticated endpoints.
    Limit is set by RATE_LIMIT_PER_MINUTE setting.
    """
    from app.db.redis import RateLimiter

    key = f"user:{current_user.user_id}"
    if not RateLimiter(redis).is_allowed(key, limit=settings.RATE_LIMIT_PER_MINUTE):
        raise RateLimitError()
    return current_user


def require_agent_rate_limit(
    current_user: User  = Depends(get_current_user),
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> User:
    """Stricter rate limit for AI agent endpoints."""
    from app.db.redis import RateLimiter

    key = f"agent:{current_user.user_id}"
    if not RateLimiter(redis).is_allowed(key, limit=settings.RATE_LIMIT_AGENT_PER_MINUTE):
        raise RateLimitError()
    return current_user


# ── Type aliases (for cleaner route signatures) ───────────────────────────────
CurrentUser      = Annotated[User, Depends(get_current_user)]
AdminUser        = Annotated[User, Depends(require_admin)]
RateLimitedUser  = Annotated[User, Depends(require_rate_limit)]
AgentUser        = Annotated[User, Depends(require_agent_rate_limit)]
DBSession        = Annotated[Session, Depends(get_db)]
UserSvc          = Annotated[UserService, Depends(get_user_service)]
