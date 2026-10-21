"""
app/services/skill_gap_service.py
──────────────────────────────────
Business logic for skill gap analysis:
  - resolve resume text from DB or uploaded bytes
  - run the analysis agent
  - persist SkillGapReport to MySQL
  - CRUD for past reports
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.skill_gap_agent import SkillGapAnalysisResult, run_skill_gap_analysis
from app.core.llm_provider import get_last_call_usage
from app.models.agent_log import AgentName
from app.services.agent_log_service import timed_agent_call
from app.agents.role_skill_db import get_role
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.notification import NotificationType
from app.models.resume import Resume
from app.models.skill_gap import GapSeverity, SkillGapReport
from app.services.notification_service import notify

logger = get_logger(__name__)


class SkillGapService:

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Analyse from resume_id ────────────────────────────────────────────────
    def analyse_from_resume(
        self,
        user_id:        int,
        resume_id:      int,
        role_key:       str,
        target_company: str | None = None,
        extra_skills:   list[str]  = None,
    ) -> SkillGapReport:
        """
        Load resume text from DB, run analysis, persist and return report.
        """
        # Validate role
        get_role(role_key)   # raises ValueError if unknown

        # Load resume
        resume: Resume | None = self._db.scalar(
            select(Resume).where(
                Resume.resume_id == resume_id,
                Resume.user_id   == user_id,
            )
        )
        if not resume:
            raise NotFoundError("Resume", resume_id)

        if not resume.raw_text or len(resume.raw_text.strip()) < 50:
            raise ValidationError(
                "Resume text is not available. "
                "Please analyse the resume first via /resume/{id}/analyse."
            )

        return self._run_and_persist(
            user_id=user_id,
            resume_id=resume_id,
            resume_text=resume.raw_text,
            role_key=role_key,
            target_company=target_company,
            extra_skills=extra_skills,
        )

    # ── Analyse from raw text ─────────────────────────────────────────────────
    def analyse_from_text(
        self,
        user_id:        int,
        resume_text:    str,
        role_key:       str,
        target_company: str | None = None,
        extra_skills:   list[str]  = None,
    ) -> SkillGapReport:
        """Run analysis from raw text (no file upload required)."""
        get_role(role_key)
        if len(resume_text.strip()) < 50:
            raise ValidationError("Resume text is too short to analyse.")
        return self._run_and_persist(
            user_id=user_id,
            resume_id=None,
            resume_text=resume_text,
            role_key=role_key,
            target_company=target_company,
            extra_skills=extra_skills,
        )

    # ── Compare against multiple roles ───────────────────────────────────────
    def compare_roles(
        self,
        user_id:      int,
        resume_id:    int,
        role_keys:    list[str],
    ) -> list[dict]:
        """
        Quick comparison of match% across multiple roles.
        Returns lightweight summary list sorted by match desc.
        Does NOT persist reports.
        """
        resume: Resume | None = self._db.scalar(
            select(Resume).where(
                Resume.resume_id == resume_id,
                Resume.user_id   == user_id,
            )
        )
        if not resume or not resume.raw_text:
            raise NotFoundError("Resume", resume_id)

        from app.agents.skill_matcher import extract_skills_from_text, match_skills
        skills  = extract_skills_from_text(resume.raw_text)
        results = []
        for rk in role_keys:
            try:
                get_role(rk)
                m = match_skills(skills, rk)
                results.append({
                    "role_key":            rk,
                    "role_title":          m.role_title,
                    "overall_match_pct":   m.overall_match_pct,
                    "required_match_pct":  m.required_match_pct,
                    "gap_severity":        m.gap_severity,
                    "matched_count":       len(m.matched),
                    "missing_critical":    sum(1 for s in m.missing_required
                                               if s.priority.value == "critical"),
                })
            except ValueError:
                pass   # skip unknown roles silently

        results.sort(key=lambda r: r["overall_match_pct"], reverse=True)
        return results

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def get_report(self, gap_report_id: int, user_id: int) -> SkillGapReport:
        report = self._db.scalar(
            select(SkillGapReport).where(
                SkillGapReport.gap_report_id == gap_report_id,
                SkillGapReport.user_id       == user_id,
            )
        )
        if not report:
            raise NotFoundError("SkillGapReport", gap_report_id)
        return report

    def list_reports(
        self,
        user_id:  int,
        role_key: str | None = None,
        limit:    int        = 20,
    ) -> list[SkillGapReport]:
        q = select(SkillGapReport).where(SkillGapReport.user_id == user_id)
        if role_key:
            q = q.where(SkillGapReport.target_role_key == role_key)
        q = q.order_by(SkillGapReport.created_at.desc()).limit(limit)
        return list(self._db.scalars(q).all())

    def delete_report(self, gap_report_id: int, user_id: int) -> None:
        report = self.get_report(gap_report_id, user_id)
        self._db.delete(report)
        self._db.flush()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _run_and_persist(
        self,
        user_id:        int,
        resume_id:      int | None,
        resume_text:    str,
        role_key:       str,
        target_company: str | None,
        extra_skills:   list[str] | None,
    ) -> SkillGapReport:
        with timed_agent_call(
            self._db, user_id=user_id, agent_name=AgentName.SKILL_GAP,
            metadata={"role_key": role_key, "target_company": target_company},
        ) as ctx:
            result: SkillGapAnalysisResult = run_skill_gap_analysis(
                resume_text=resume_text,
                role_key=role_key,
                target_company=target_company,
                extra_skills=extra_skills or [],
            )
            usage = get_last_call_usage()
            ctx["input_tokens"]  = usage.get("input_tokens")
            ctx["output_tokens"] = usage.get("output_tokens")

        report = SkillGapReport(
            user_id=user_id,
            resume_id=resume_id,
            target_role_key=role_key,
            target_role_title=result.role_title,
            target_company=target_company,

            overall_match_pct=result.overall_match_pct,
            required_match_pct=result.required_match_pct,
            preferred_match_pct=result.preferred_match_pct,
            gap_severity=GapSeverity(result.gap_severity),

            matched_skills=result.matched_skills,
            missing_required=result.missing_required,
            missing_preferred=result.missing_preferred,

            executive_summary=result.executive_summary,
            detailed_feedback=result.detailed_feedback,
            learning_priorities=result.learning_priorities,
            recommended_courses=result.recommended_courses,
            recommended_projects=result.recommended_projects,
            recommended_certs=result.recommended_certs,
            quick_wins=result.quick_wins,
            strengths=result.strengths,
            salary_insight=result.salary_insight,
            estimated_prep_months=result.estimated_prep_months,

            model_used=result.model_used,
            tokens_consumed=result.tokens_consumed,
            processing_time_ms=result.processing_time_ms,
        )
        self._db.add(report)
        self._db.flush()

        notify(
            self._db,
            user_id=user_id,
            type=NotificationType.SKILL_GAP_REPORT_COMPLETED,
            title="Skill gap report ready",
            message=f"Your match for {result.role_title} is {result.overall_match_pct}%.",
            action_url=f"/skill-gap/reports/{report.gap_report_id}",
        )

        logger.info(
            "skill_gap_report_saved",
            report_id=report.gap_report_id,
            user_id=user_id,
            role=role_key,
            match=result.overall_match_pct,
        )
        return report
