"""
app/schemas/resume.py
─────────────────────
Pydantic v2 request/response schemas for the Resume Analyzer Agent.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Sub-schemas returned inside the full report ───────────────────────────────

class ContactInfo(BaseModel):
    name:     str | None = None
    email:    str | None = None
    phone:    str | None = None
    location: str | None = None
    linkedin: str | None = None
    github:   str | None = None
    website:  str | None = None


class ExtractedSkill(BaseModel):
    name:        str
    category:    str   = "general"   # e.g. language, framework, tool, soft
    proficiency: str | None = None   # inferred: beginner/intermediate/advanced
    years:       int | None = None


class ExtractedProject(BaseModel):
    title:        str
    description:  str | None = None
    technologies: list[str]  = []
    impact:       str | None = None   # quantified result if found
    url:          str | None = None


class ExtractedCertification(BaseModel):
    name:        str
    issuer:      str | None = None
    year:        int | None = None
    expiry_year: int | None = None
    credential_id: str | None = None


class ExtractedEducation(BaseModel):
    degree:      str | None = None
    institution: str | None = None
    field:       str | None = None
    year:        int | None = None
    gpa:         str | None = None


class ExtractedExperience(BaseModel):
    title:        str
    company:      str | None = None
    start_date:   str | None = None
    end_date:     str | None = None
    is_current:   bool = False
    description:  str | None = None
    achievements: list[str]  = []
    technologies: list[str]  = []


class ScoreBreakdown(BaseModel):
    ats_score:        float = Field(..., ge=0, le=100, description="Overall ATS score 0-100")
    formatting_score: float = Field(..., ge=0, le=100)
    content_score:    float = Field(..., ge=0, le=100)
    keyword_score:    float = Field(..., ge=0, le=100)
    experience_score: float = Field(..., ge=0, le=100)
    grade:            str   = Field(..., description="A/B/C/D/F letter grade")
    verdict:          str   = Field(..., description="Short human-readable verdict")


class ImprovementSuggestion(BaseModel):
    category:    str   # formatting | content | keywords | experience
    issue:       str
    suggestion:  str
    priority:    str   # high | medium | low


# ── Upload response ───────────────────────────────────────────────────────────

class ResumeUploadResponse(BaseModel):
    resume_id:  int
    filename:   str
    status:     str
    message:    str


# ── Full analysis report ──────────────────────────────────────────────────────

class ResumeAnalysisReport(BaseModel):
    report_id:           int
    resume_id:           int
    user_id:             int
    filename:            str

    # Scores
    scores:              ScoreBreakdown

    # Extracted entities
    contact_info:        ContactInfo
    skills:              list[ExtractedSkill]
    technical_skills:    list[str]
    soft_skills:         list[str]
    projects:            list[ExtractedProject]
    certifications:      list[ExtractedCertification]
    education:           list[ExtractedEducation]
    experience:          list[ExtractedExperience]
    total_years_experience: float

    # Analysis
    summary:             str
    strengths:           list[str]
    improvements:        list[ImprovementSuggestion]
    keywords_found:      list[str]
    keywords_missing:    list[str]
    seniority_match:     str
    seniority_detected:  str | None

    # Meta
    page_count:          int
    word_count:          int
    model_used:          str
    processing_time_ms:  int
    created_at:          datetime

    model_config = {"from_attributes": True}


# ── List item (lightweight, for listing all resumes) ─────────────────────────

class ResumeListItem(BaseModel):
    resume_id:       int
    filename:        str
    status:          str
    is_primary:      bool
    ats_score:       float | None = None
    created_at:      datetime

    model_config = {"from_attributes": True}


# ── Standard envelope ─────────────────────────────────────────────────────────

class APIResponse(BaseModel):
    success: bool = True
    message: str  = "OK"
    data:    Any  = None
