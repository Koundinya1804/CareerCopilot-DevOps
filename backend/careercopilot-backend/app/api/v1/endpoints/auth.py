"""
app/api/v1/endpoints/auth.py
────────────────────────────
Authentication endpoints:

  POST /api/v1/auth/register   — create new user account
  POST /api/v1/auth/login      — exchange credentials for JWT pair
  POST /api/v1/auth/refresh    — rotate access token via refresh token
  POST /api/v1/auth/logout     — revoke refresh token (add to blacklist)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from jose import JWTError
from redis import Redis
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, DBSession
from app.core.config import settings
from app.core.exceptions import TokenInvalidError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    extract_token_jti,
)
from app.db.redis import TokenBlacklist, get_redis
from app.db.session import get_db
from app.schemas.user import (
    APIResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    TokenPair,
    UserRegisterRequest,
    UserRegisterResponse,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


# ── Register ──────────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    payload: UserRegisterRequest,
    db:      DBSession,
) -> APIResponse:
    """
    Create a new user with email + password.

    - **full_name**: 2–150 characters
    - **email**: must be unique across the platform
    - **password**: min 8 chars, requires uppercase and digit
    """
    svc  = UserService(db)
    user = svc.register(payload)

    logger.info("register_success", user_id=user.user_id, email=user.email)
    return APIResponse(
        message="Account created successfully. You may now log in.",
        data=UserRegisterResponse.model_validate(user),
    )


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post(
    "/login",
    response_model=APIResponse,
    summary="Authenticate and receive JWT token pair",
)
def login(
    payload: LoginRequest,
    db:      DBSession,
) -> APIResponse:
    """
    Exchange email + password for an access token (15 min) and
    a refresh token (7 days).

    Include the access token as:  `Authorization: Bearer <token>`
    """
    svc  = UserService(db)
    user = svc.authenticate(payload.email, payload.password)

    access_token  = create_access_token(user.user_id, user.role.value)
    refresh_token = create_refresh_token(user.user_id, user.role.value)

    logger.info("login_success", user_id=user.user_id)
    return APIResponse(
        message="Login successful.",
        data=LoginResponse(
            user=UserRegisterResponse.model_validate(user),
            tokens=TokenPair(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            ),
        ),
    )


# ── Refresh ───────────────────────────────────────────────────────────────────
@router.post(
    "/refresh",
    response_model=APIResponse,
    summary="Rotate access token using a valid refresh token",
)
def refresh(
    payload: RefreshTokenRequest,
    db:      DBSession,
    redis:   Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    """
    Exchange a valid refresh token for a new access token.
    The refresh token itself is **not** rotated (single-use rotation is opt-in).
    """
    try:
        claims = decode_token(payload.refresh_token)
    except JWTError:
        raise TokenInvalidError()

    if claims.get("type") != "refresh":
        raise TokenInvalidError()

    jti = str(claims.get("jti", ""))
    if jti and TokenBlacklist(redis).is_revoked(jti):
        raise TokenInvalidError()

    user_id = int(claims["sub"])
    role    = str(claims["role"])

    # Confirm user still active
    svc  = UserService(db)
    user = svc.get_by_id(user_id)

    new_access = create_access_token(user.user_id, user.role.value)
    logger.info("token_refreshed", user_id=user.user_id)

    return APIResponse(
        message="Token refreshed.",
        data=TokenPair(
            access_token=new_access,
            refresh_token=payload.refresh_token,  # unchanged
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )


# ── Logout ────────────────────────────────────────────────────────────────────
@router.post(
    "/logout",
    response_model=APIResponse,
    summary="Revoke the current refresh token",
)
def logout(
    payload:      RefreshTokenRequest,
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    """
    Revoke the provided refresh token by adding its jti to the Redis blacklist.
    The client must discard both tokens locally.
    """
    jti = extract_token_jti(payload.refresh_token)
    if jti:
        TokenBlacklist(redis).revoke(jti)

    logger.info("user_logged_out", user_id=current_user.user_id)
    return APIResponse(message="Logged out successfully.")
