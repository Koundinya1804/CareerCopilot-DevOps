"""
app/services/career_recommendation_service.py
───────────────────────────────────────────────
Business logic for career recommendations:
  - analyse_from_resume()   — load resume from DB, run agent, persist
  - analyse_from_profile()  — use user profile + explicit inputs
  - get_report()            — fetch persisted report
  - list_reports()          — user's recommendation history
  - get_quick_comparison()  — fast role score comparison (no Gemini)
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.career_recommendation_agent import (
    CareerRecommendationOutput,
    run_career_recommendation,
)
from app.agents.recommendation_engine import score_all_roles
from app.core.exceptions import NotFoundError, ValidationError
from app.core.llm_provider import get_last_call_usage
from app.core.logging import get_logger
from app.models.agent_log import AgentName
from app.models.career_recommendation import CareerRecommendationReport, RecommendationStatus
from app.models.notification import NotificationType
from app.models.resume import Resume
from app.services.agent_log_service import timed_agent_call
from app.services.notification_service import notify

logger = get_logger(__name__)


class CareerRecommendationService:

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── Analyse from resume ────────────────────────────────────────────────────
    def analyse_from_resume(
        self,
        user_id:    int,
        resume_id:  int,
        interests:  list[str],
        extra_skills: list[str] | None = None,
    ) -> CareerRecommendationReport:
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
                "Resume text not available. Analyse the resume first via "
                "/resume/{id}/analyse before requesting career recommendations."
            )

        from app.agents.skill_matcher import extract_skills_from_text
        skills = list({*extract_skills_from_text(resume.raw_text), *(extra_skills or [])})
        edu    = self._infer_education(resume.raw_text)
        years  = self._infer_years(resume.raw_text)

        return self._run_and_persist(
            user_id=user_id,
            resume_id=resume_id,
            resume_text=resume.raw_text,
            skills=skills,
            interests=interests,
            years_experience=years,
            education_level=edu,
        )

    # ── Analyse from explicit profile inputs ──────────────────────────────────
    def analyse_from_profile(
        self,
        user_id:          int,
        skills:           list[str],
        interests:        list[str],
        years_experience: float,
        education_level:  str,
        resume_text:      str = "",
    ) -> CareerRecommendationReport:
        if not skills:
            raise ValidationError("At least one skill is required for recommendations.")
        return self._run_and_persist(
            user_id=user_id,
            resume_id=None,
            resume_text=resume_text,
            skills=skills,
            interests=interests,
            years_experience=years_experience,
            education_level=education_level,
        )

    # ── Quick comparison (no Gemini, no DB write) ─────────────────────────────
    def quick_comparison(
        self,
        skills:           list[str],
        interests:        list[str],
        years_experience: float,
        education_level:  str,
    ) -> list[dict]:
        result = score_all_roles(
            candidate_skills=skills,
            interests=interests,
            years_experience=years_experience,
            education_level=education_level,
        )
        return [
            {
                "role_key":        rs.role_key,
                "role_title":      rs.role_title,
                "role_icon":       rs.role_icon,
                "domain":          rs.domain,
                "overall_score":   rs.overall_score,
                "suitability_label": rs.suitability_label,
            }
            for rs in result.all_scores
        ]

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def get_report(self, report_id: int, user_id: int) -> CareerRecommendationReport:
        r = self._db.scalar(
            select(CareerRecommendationReport).where(
                CareerRecommendationReport.report_id == report_id,
                CareerRecommendationReport.user_id   == user_id,
            )
        )
        if not r:
            raise NotFoundError("CareerRecommendationReport", report_id)
        return r

    def list_reports(self, user_id: int, limit: int = 10) -> list[CareerRecommendationReport]:
        return list(self._db.scalars(
            select(CareerRecommendationReport)
            .where(CareerRecommendationReport.user_id == user_id)
            .order_by(CareerRecommendationReport.created_at.desc())
            .limit(limit)
        ).all())

    def delete_report(self, report_id: int, user_id: int) -> None:
        r = self.get_report(report_id, user_id)
        self._db.delete(r)
        self._db.flush()

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _run_and_persist(
        self,
        user_id:          int,
        resume_id:        int | None,
        resume_text:      str,
        skills:           list[str],
        interests:        list[str],
        years_experience: float,
        education_level:  str,
    ) -> CareerRecommendationReport:
        with timed_agent_call(
            self._db, user_id=user_id, agent_name=AgentName.CAREER_RECOMMENDATION,
            metadata={"resume_id": resume_id},
        ) as ctx:
            out: CareerRecommendationOutput = run_career_recommendation(
                resume_text=resume_text,
                skills=skills,
                interests=interests,
                years_experience=years_experience,
                education_level=education_level,
            )
            usage = get_last_call_usage()
            ctx["input_tokens"]  = usage.get("input_tokens")
            ctx["output_tokens"] = usage.get("output_tokens")

        top_role  = out.recommended_roles[0] if out.recommended_roles else None

        report = CareerRecommendationReport(
            user_id=user_id,
            resume_id=resume_id,
            input_skills={"skills": skills[:30]},
            input_interests={"interests": interests[:15]},
            input_experience_years=years_experience,
            input_education_level=education_level,
            top_recommended_role=top_role.role_key if top_role else None,
            top_role_score=top_role.suitability_score if top_role else 0.0,
            recommended_roles={
                "roles": [
                    {
                        "rank":               r.rank,
                        "role_key":           r.role_key,
                        "role_title":         r.role_title,
                        "role_icon":          r.role_icon,
                        "domain":             r.domain,
                        "suitability_score":  r.suitability_score,
                        "suitability_label":  r.suitability_label,
                        "confidence":         r.confidence,
                        "skill_match_pct":    r.skill_match_pct,
                        "interest_match_pct": r.interest_match_pct,
                        "why_suited":         r.why_suited,
                        "what_youll_do":      r.what_youll_do,
                        "skill_gaps":         r.skill_gaps,
                        "salary_journey":     r.salary_journey,
                        "top_companies":      r.top_companies,
                        "related_roles":      r.related_roles,
                        "transition_timeline": r.transition_timeline,
                    }
                    for r in out.recommended_roles
                ],
                "all_scores":  out.all_role_scores,
                "domain_fit":  out.domain_fit,
                "best_domain": out.best_domain,
            },
            career_narrative=out.career_narrative,
            personality_profile=out.personality_profile,
            industry_insights={"text": out.industry_insights},
            action_plan=out.action_plan,
            market_trends=out.market_trends,
            status=RecommendationStatus.COMPLETE,
            model_used=out.model_used,
            tokens_consumed=out.tokens_consumed,
            processing_time_ms=out.processing_time_ms,
        )
        self._db.add(report)
        self._db.flush()

        notify(
            self._db,
            user_id=user_id,
            type=NotificationType.CAREER_RECOMMENDATION_COMPLETED,
            title="Career recommendation ready",
            message=(
                f"Top match: {top_role.role_title} ({top_role.suitability_score:.0f}% fit)."
                if top_role else "Your career recommendation report is ready."
            ),
            action_url=f"/career/reports/{report.report_id}",
        )

        logger.info("career_rec_report_saved",
                    report_id=report.report_id, top_role=report.top_recommended_role)
        return report

    @staticmethod
    def _infer_education(text: str) -> str:
        from app.utils.nlp_extractor import _extract_education
        level, _ = _extract_education(text, {})
        return level or "Bachelors"

    @staticmethod
    def _infer_years(text: str) -> float:
        from app.utils.nlp_extractor import _extract_date_ranges, _calculate_years_experience
        ranges = _extract_date_ranges(text)
        return _calculate_years_experience(ranges)
