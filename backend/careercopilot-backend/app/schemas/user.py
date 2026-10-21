"""
app/schemas/user.py
───────────────────
Pydantic v2 request / response schemas for user management and authentication.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Shared base ───────────────────────────────────────────────────────────────
class APIResponse(BaseModel):
    """Standard envelope for all API responses."""
    success: bool = True
    message: str  = "OK"
    data:    Any  = None


# ── Registration ──────────────────────────────────────────────────────────────
class UserRegisterRequest(BaseModel):
    full_name: str       = Field(..., min_length=2, max_length=150, examples=["Priya Sharma"])
    email:     EmailStr  = Field(..., examples=["priya@example.com"])
    password:  str       = Field(..., min_length=8, max_length=72, examples=["Str0ng!Pass"])

    @field_validator("full_name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Full name must not be blank.")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserRegisterResponse(BaseModel):
    user_id:    int
    email:      str
    full_name:  str
    role:       str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Login ─────────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email:    EmailStr = Field(..., examples=["priya@example.com"])
    password: str      = Field(..., min_length=1, examples=["Str0ng!Pass"])


class TokenPair(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int  # seconds until access token expires


class LoginResponse(BaseModel):
    user:   UserRegisterResponse
    tokens: TokenPair


# ── Token Refresh ─────────────────────────────────────────────────────────────
class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


# ── Profile ───────────────────────────────────────────────────────────────────
class UserProfileRequest(BaseModel):
    target_role:          str | None = Field(None, max_length=150)
    current_role:         str | None = Field(None, max_length=150)
    years_experience:     int        = Field(0, ge=0, le=50)
    location:             str | None = Field(None, max_length=150)
    linkedin_url:         str | None = Field(None, max_length=500)
    github_url:           str | None = Field(None, max_length=500)
    bio:                  str | None = Field(None, max_length=2000)
    preferred_industries: list[str]  = Field(default_factory=list)


class UserProfileResponse(BaseModel):
    profile_id:           int
    user_id:              int
    target_role:          str | None
    current_role:         str | None
    years_experience:     int
    location:             str | None
    linkedin_url:         str | None
    github_url:           str | None
    bio:                  str | None
    preferred_industries: list[str] | None
    created_at:           datetime
    updated_at:           datetime

    model_config = {"from_attributes": True}


# ── Skill ─────────────────────────────────────────────────────────────────────
class SkillAddRequest(BaseModel):
    skill_name:  str = Field(..., min_length=1, max_length=100, examples=["Python"])
    proficiency: str = Field("intermediate", examples=["intermediate"])
    years_used:  int = Field(0, ge=0, le=50)


class SkillResponse(BaseModel):
    skill_id:   int
    skill_name: str
    proficiency: str
    years_used: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Me (current user) ─────────────────────────────────────────────────────────
class MeResponse(BaseModel):
    user_id:    int
    email:      str
    full_name:  str
    role:       str
    status:     str
    avatar_url: str | None
    created_at: datetime
    profile:    UserProfileResponse | None = None
    skills:     list[SkillResponse]        = []

    model_config = {"from_attributes": True}
