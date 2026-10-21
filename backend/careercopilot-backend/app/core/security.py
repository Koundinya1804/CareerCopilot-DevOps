"""
app/core/security.py
────────────────────
Password hashing (bcrypt) and JWT access / refresh token utilities.

Token payload claims:
  sub  : str  — user_id (as string)
  role : str  — user role
  type : str  — "access" | "refresh"
  jti  : str  — unique token ID (for refresh-token revocation via Redis)
  exp  : int  — UNIX expiry timestamp
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Password Hashing ─────────────────────────────────────────────────────────
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plain: str) -> str:
    """Return bcrypt hash of *plain* password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return _pwd_context.verify(plain, hashed)


# ── JWT Helpers ───────────────────────────────────────────────────────────────
TokenType = Literal["access", "refresh"]


def _create_token(
    subject: str,
    role: str,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    """Internal: build and sign a JWT."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    token: str = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    logger.debug(
        "token_created",
        token_type=token_type,
        subject=subject,
        expires_in_seconds=int(expires_delta.total_seconds()),
    )
    return token


def create_access_token(user_id: int, role: str) -> str:
    """Return a short-lived JWT access token."""
    return _create_token(
        subject=str(user_id),
        role=role,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int, role: str) -> str:
    """Return a long-lived JWT refresh token."""
    return _create_token(
        subject=str(user_id),
        role=role,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises:
        JWTError — invalid signature, expired, or malformed token.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        logger.warning("token_decode_failed", token_prefix=token[:20] + "…")
        raise


def extract_token_jti(token: str) -> str | None:
    """Extract the jti claim without full validation (for revocation logging)."""
    try:
        claims = jwt.get_unverified_claims(token)
        return str(claims.get("jti", ""))
    except JWTError:
        return None
