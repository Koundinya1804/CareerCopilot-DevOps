"""
app/db/redis.py
───────────────
Redis client wrapper.  Provides:
  - get_redis()         : FastAPI dependency
  - TokenBlacklist      : revoke refresh tokens on logout
  - RateLimiter         : sliding-window rate limiting helper
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import redis
from redis import Redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Client pool (singleton) ───────────────────────────────────────────────────
_redis_pool = redis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=50,
)


def get_redis_client() -> Redis:  # type: ignore[type-arg]
    return redis.Redis(connection_pool=_redis_pool)


def get_redis() -> Generator[Redis, None, None]:  # type: ignore[type-arg]
    """FastAPI dependency: yields a Redis client from the shared pool."""
    client = get_redis_client()
    try:
        yield client
    finally:
        pass  # pool manages connection lifecycle


# ── Token Blacklist ───────────────────────────────────────────────────────────
_BLACKLIST_PREFIX = "blacklist:jti:"


class TokenBlacklist:
    """
    Revoke refresh tokens on logout by storing their jti in Redis.
    TTL is aligned with REFRESH_TOKEN_EXPIRE_DAYS so Redis auto-cleans.
    """

    def __init__(self, client: Redis) -> None:  # type: ignore[type-arg]
        self._r = client

    def revoke(self, jti: str) -> None:
        ttl = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self._r.setex(f"{_BLACKLIST_PREFIX}{jti}", ttl, "1")
        logger.info("token_revoked", jti=jti)

    def is_revoked(self, jti: str) -> bool:
        return self._r.exists(f"{_BLACKLIST_PREFIX}{jti}") == 1


# ── Rate Limiter ──────────────────────────────────────────────────────────────
_RATE_PREFIX = "rate:"


class RateLimiter:
    """
    Sliding-window rate limiter backed by Redis.

    Usage:
        limiter = RateLimiter(redis_client)
        if not limiter.is_allowed("user:42", limit=10, window_seconds=60):
            raise RateLimitError()
    """

    def __init__(self, client: Redis) -> None:  # type: ignore[type-arg]
        self._r = client

    def is_allowed(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        redis_key = f"{_RATE_PREFIX}{key}"
        pipe = self._r.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds)
        count, _ = pipe.execute()
        allowed: bool = int(count) <= limit
        if not allowed:
            logger.warning("rate_limit_exceeded", key=key, count=count, limit=limit)
        return allowed


# ── Health Check ──────────────────────────────────────────────────────────────
def check_redis_connection() -> bool:
    try:
        client = get_redis_client()
        client.ping()
        logger.info("redis_connection_ok", host=settings.REDIS_HOST)
        return True
    except Exception as exc:
        logger.error("redis_connection_failed", error=str(exc))
        return False
