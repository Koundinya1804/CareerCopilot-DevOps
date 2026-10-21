"""
app/api/v1/endpoints/users.py
──────────────────────────────
User management endpoints (all protected — require valid JWT):

  GET    /api/v1/users/me                — current user + profile + skills
  PUT    /api/v1/users/me/profile        — upsert career profile
  POST   /api/v1/users/me/skills         — add / update a skill
  DELETE /api/v1/users/me/skills/{id}    — remove a skill

  GET    /api/v1/users/{id}              — admin: get any user by ID
  GET    /api/v1/users                   — admin: paginated user list
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.dependencies import AdminUser, CurrentUser, DBSession, UserSvc
from app.core.logging import get_logger
from app.models.user import User
from app.schemas.user import (
    APIResponse,
    MeResponse,
    SkillAddRequest,
    SkillResponse,
    UserProfileRequest,
    UserProfileResponse,
    UserRegisterResponse,
)

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


# ── Current User ──────────────────────────────────────────────────────────────
@router.get(
    "/me",
    response_model=APIResponse,
    summary="Get the authenticated user's full profile",
)
def get_me(current_user: CurrentUser) -> APIResponse:
    """
    Returns the authenticated user including their career profile and skill list.
    """
    return APIResponse(data=MeResponse.model_validate(current_user))


# ── Profile ───────────────────────────────────────────────────────────────────
@router.put(
    "/me/profile",
    response_model=APIResponse,
    summary="Create or update career profile",
)
def upsert_profile(
    payload:      UserProfileRequest,
    current_user: CurrentUser,
    svc:          UserSvc,
) -> APIResponse:
    """
    Upserts the authenticated user's career profile.
    All fields are optional — omit to leave unchanged.
    """
    profile = svc.upsert_profile(current_user.user_id, payload)
    return APIResponse(
        message="Profile updated.",
        data=UserProfileResponse.model_validate(profile),
    )


# ── Skills ────────────────────────────────────────────────────────────────────
@router.post(
    "/me/skills",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add or update a skill",
)
def add_skill(
    payload:      SkillAddRequest,
    current_user: CurrentUser,
    svc:          UserSvc,
) -> APIResponse:
    skill = svc.add_skill(current_user.user_id, payload)
    return APIResponse(
        message="Skill saved.",
        data=SkillResponse.model_validate(skill),
    )


@router.delete(
    "/me/skills/{skill_id}",
    response_model=APIResponse,
    summary="Remove a skill",
)
def delete_skill(
    skill_id:     int,
    current_user: CurrentUser,
    svc:          UserSvc,
) -> APIResponse:
    svc.delete_skill(current_user.user_id, skill_id)
    return APIResponse(message="Skill removed.")


# ── Admin: User Lookup ────────────────────────────────────────────────────────
@router.get(
    "",
    response_model=APIResponse,
    summary="[Admin] Paginated user list",
)
def list_users(
    _:      AdminUser,
    db:     DBSession,
    page:   int = Query(1,  ge=1),
    size:   int = Query(20, ge=1, le=100),
) -> APIResponse:
    offset = (page - 1) * size
    total  = db.scalar(select(func.count(User.user_id))) or 0
    users  = db.scalars(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(size)
    ).all()

    return APIResponse(
        data={
            "total":   total,
            "page":    page,
            "size":    size,
            "pages":   (total + size - 1) // size,
            "items":   [UserRegisterResponse.model_validate(u) for u in users],
        }
    )


@router.get(
    "/{user_id}",
    response_model=APIResponse,
    summary="[Admin] Get user by ID",
)
def get_user_by_id(
    user_id: int,
    _:       AdminUser,
    svc:     UserSvc,
) -> APIResponse:
    user = svc.get_by_id(user_id)
    return APIResponse(data=MeResponse.model_validate(user))
