"""
app/api/v1/router.py — Master API router

Registers all module endpoint routers under /api/v1.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    users,
    resume,
    skill_gap,
    career,
    interview,
    rag,
    agent_chat,
    admin,
)

api_router = APIRouter()

# ── Public ────────────────────────────────────────────────────────────────────
api_router.include_router(auth.router,        prefix="/auth",        tags=["Authentication"])

# ── Authenticated user routes ─────────────────────────────────────────────────
api_router.include_router(users.router,       prefix="/users",       tags=["Users"])
api_router.include_router(resume.router,      prefix="/resume",      tags=["Resume Analyser"])
api_router.include_router(skill_gap.router,   prefix="/skill-gap",   tags=["Skill Gap Analyser"])
api_router.include_router(career.router,      prefix="/career",      tags=["Career Agent"])
api_router.include_router(interview.router,   prefix="/interview",   tags=["Interview Coach"])
api_router.include_router(rag.router,         prefix="/rag",         tags=["RAG System"])
api_router.include_router(agent_chat.router,  prefix="/agent-chat",  tags=["Supervisor Agent"])

# ── Admin-only routes ─────────────────────────────────────────────────────────
api_router.include_router(admin.router,       tags=["Admin Panel"])
