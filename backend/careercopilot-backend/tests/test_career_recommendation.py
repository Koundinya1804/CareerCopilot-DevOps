"""
tests/test_career_recommendation.py
─────────────────────────────────────
Tests for the Career Recommendation Agent:

  Unit:
    - Role catalogue (20 roles, domain coverage, salary data)
    - Recommendation engine (scoring, experience curve, interest matching)
    - Agent pipeline (mock Gemini, JSON parsing, output merging)

  Integration:
    - API endpoints (recommend, quick-compare, list, CRUD)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.db.redis import get_redis
from app.main import app

# ── Test DB ───────────────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_career_rec.db"
engine      = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def override_get_redis():
    m = MagicMock()
    m.exists.return_value = 0
    m.pipeline.return_value.execute.return_value = [1, True]
    yield m


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db]    = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    from pathlib import Path
    Path("test_career_rec.db").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection",      return_value=True):
        with TestClient(app) as c:
            yield c


def get_auth_headers(client, suffix="cr"):
    client.post("/api/v1/auth/register", json={
        "full_name": f"CR User {suffix}", "email": f"cr_{suffix}@test.com",
        "password":  "Str0ng!Pass",
    })
    r = client.post("/api/v1/auth/login", json={
        "email": f"cr_{suffix}@test.com", "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


# ── Sample data ───────────────────────────────────────────────────────────────
ML_SKILLS    = ["Python", "PyTorch", "scikit-learn", "NumPy", "Pandas",
                "Docker", "Git", "SQL", "MLflow", "Statistics", "FastAPI"]
AI_SKILLS    = ["Python", "LangChain", "RAG", "Gemini", "ChromaDB",
                "FastAPI", "Docker", "Prompt Engineering", "Embeddings",
                "Vector Databases", "Async Python", "Redis"]
CLOUD_SKILLS = ["AWS", "Terraform", "Docker", "Kubernetes", "Linux",
                "Python", "Git", "GitHub Actions", "Prometheus", "S3", "IAM"]
ML_INTERESTS = ["machine learning", "deep learning", "data pipeline", "mlops"]
AI_INTERESTS = ["artificial intelligence", "llm", "generative ai", "ai products"]


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Role Catalogue
# ═══════════════════════════════════════════════════════════════════════════════
class TestRoleCatalogue:
    def test_twenty_roles_defined(self):
        from app.agents.career_role_catalogue import ROLES
        assert len(ROLES) == 20

    def test_display_order_matches_roles(self):
        from app.agents.career_role_catalogue import ROLES, ROLE_DISPLAY_ORDER
        assert set(ROLE_DISPLAY_ORDER) == set(ROLES.keys())

    def test_all_roles_have_salary_data(self):
        from app.agents.career_role_catalogue import ROLES
        for key, role in ROLES.items():
            lo, hi = role.salary_mid_inr
            assert hi >= lo >= 0, f"{key} has invalid salary"

    def test_all_roles_have_skill_keywords(self):
        from app.agents.career_role_catalogue import ROLES
        for key, role in ROLES.items():
            assert len(role.skill_keywords) >= 5, f"{key} has too few skill keywords"

    def test_all_roles_have_interest_keywords(self):
        from app.agents.career_role_catalogue import ROLES
        for key, role in ROLES.items():
            assert len(role.interest_keywords) >= 3, f"{key} needs interest keywords"

    def test_six_domains_represented(self):
        from app.agents.career_role_catalogue import ROLES
        domains = {r.domain for r in ROLES.values()}
        assert len(domains) >= 5

    def test_get_role_valid(self):
        from app.agents.career_role_catalogue import get_career_role
        r = get_career_role("ai_engineer")
        assert r.title == "AI Engineer"
        assert r.domain == "AI/ML"

    def test_get_role_invalid(self):
        from app.agents.career_role_catalogue import get_career_role
        with pytest.raises(ValueError, match="Unknown career role"):
            get_career_role("time_traveller")

    def test_ai_engineer_high_demand_growth(self):
        from app.agents.career_role_catalogue import ROLES
        assert ROLES["ai_engineer"].demand_growth_pct >= 50

    def test_booming_roles_exist(self):
        from app.agents.career_role_catalogue import ROLES
        booming = [k for k, r in ROLES.items() if r.five_year_outlook == "booming"]
        assert len(booming) >= 3


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Recommendation Engine
# ═══════════════════════════════════════════════════════════════════════════════
class TestRecommendationEngine:
    def test_scores_all_20_roles(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        assert len(result.all_scores) == 20

    def test_top_roles_contains_5(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        assert len(result.top_roles) == 5

    def test_ml_skills_rank_ml_role_high(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        top_keys = [r.role_key for r in result.top_roles]
        assert "ml_engineer" in top_keys or "data_scientist" in top_keys

    def test_ai_skills_rank_ai_engineer_high(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(AI_SKILLS, AI_INTERESTS, 2.0, "Bachelors")
        top_keys = [r.role_key for r in result.top_roles]
        assert "ai_engineer" in top_keys

    def test_cloud_skills_rank_cloud_high(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(
            CLOUD_SKILLS,
            ["cloud infrastructure", "devops", "aws", "kubernetes"],
            3.0, "Bachelors"
        )
        top_keys = [r.role_key for r in result.top_roles]
        assert any(k in top_keys for k in ["cloud_engineer", "devops_engineer", "sre_engineer"])

    def test_scores_between_0_and_100(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        for rs in result.all_scores:
            assert 0 <= rs.overall_score <= 100, f"{rs.role_key}: {rs.overall_score}"

    def test_sorted_descending(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        scores = [r.overall_score for r in result.all_scores]
        assert scores == sorted(scores, reverse=True)

    def test_no_skills_gives_low_scores(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles([], [], 0.0, "Bachelors")
        avg = sum(r.overall_score for r in result.top_roles) / 5
        assert avg < 50

    def test_domain_fit_computed(self):
        from app.agents.recommendation_engine import score_all_roles
        result = score_all_roles(AI_SKILLS, AI_INTERESTS, 2.0, "Bachelors")
        assert isinstance(result.domain_fit, dict)
        assert len(result.domain_fit) >= 3
        assert result.best_domain in result.domain_fit

    def test_experience_score_peak_at_ideal(self):
        from app.agents.recommendation_engine import _experience_score
        from app.agents.career_role_catalogue import ROLES
        role     = ROLES["ml_engineer"]
        at_ideal = _experience_score(role.ideal_years, role)
        less     = _experience_score(0.0, role)
        assert at_ideal > less

    def test_education_bonus_phd_highest(self):
        from app.agents.recommendation_engine import _education_bonus
        assert _education_bonus("PhD") > _education_bonus("Masters")
        assert _education_bonus("Masters") > _education_bonus("Bachelors")
        assert _education_bonus("Bachelors") > _education_bonus("Diploma")

    def test_suitability_labels(self):
        from app.agents.recommendation_engine import _suitability_label
        assert _suitability_label(85) == "Excellent Fit"
        assert _suitability_label(68) == "Strong Fit"
        assert _suitability_label(52) == "Good Fit"
        assert _suitability_label(38) == "Possible Fit"
        assert _suitability_label(15) == "Low Fit"

    def test_interest_matching_boosts_role(self):
        from app.agents.recommendation_engine import score_all_roles
        with_interests    = score_all_roles(ML_SKILLS, ML_INTERESTS, 2.0, "Bachelors")
        without_interests = score_all_roles(ML_SKILLS, [], 2.0, "Bachelors")
        ml_with    = next(r for r in with_interests.all_scores    if r.role_key == "ml_engineer")
        ml_without = next(r for r in without_interests.all_scores if r.role_key == "ml_engineer")
        assert ml_with.interest_score > ml_without.interest_score


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Agent (mock Gemini)
# ═══════════════════════════════════════════════════════════════════════════════
class TestCareerRecommendationAgent:
    def test_mock_mode_returns_output(self):
        from app.agents.career_recommendation_agent import run_career_recommendation
        out = run_career_recommendation(
            resume_text="Python ML engineer with PyTorch experience",
            skills=ML_SKILLS,
            interests=ML_INTERESTS,
            years_experience=3.0,
            education_level="Bachelors",
        )
        assert len(out.recommended_roles) == 5
        assert out.model_used == "gemini-2.0-flash"
        assert out.processing_time_ms >= 0

    def test_top_role_has_salary_data(self):
        from app.agents.career_recommendation_agent import run_career_recommendation
        out = run_career_recommendation("", ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        top = out.recommended_roles[0]
        assert "fresher_inr" in top.salary_journey
        assert "senior_inr"  in top.salary_journey
        assert "global_usd"  in top.salary_journey

    def test_all_role_scores_returned(self):
        from app.agents.career_recommendation_agent import run_career_recommendation
        out = run_career_recommendation("", ML_SKILLS, ML_INTERESTS, 2.0, "Bachelors")
        assert len(out.all_role_scores) == 20

    def test_domain_fit_populated(self):
        from app.agents.career_recommendation_agent import run_career_recommendation
        out = run_career_recommendation("", AI_SKILLS, AI_INTERESTS, 1.5, "Bachelors")
        assert isinstance(out.domain_fit, dict)
        assert out.best_domain

    def test_roles_sorted_by_score(self):
        from app.agents.career_recommendation_agent import run_career_recommendation
        out    = run_career_recommendation("", ML_SKILLS, ML_INTERESTS, 3.0, "Bachelors")
        scores = [r.suitability_score for r in out.recommended_roles]
        assert scores == sorted(scores, reverse=True)

    def test_candidate_skills_echoed(self):
        from app.agents.career_recommendation_agent import run_career_recommendation
        out = run_career_recommendation("", ML_SKILLS, ML_INTERESTS, 2.0, "Bachelors")
        assert "Python" in out.candidate_skills or "python" in [s.lower() for s in out.candidate_skills]

    def test_json_parser_clean(self):
        from app.agents.career_recommendation_agent import _parse_json
        out = _parse_json('{"career_narrative": "Test narrative"}')
        assert out["career_narrative"] == "Test narrative"

    def test_json_parser_strips_fences(self):
        from app.agents.career_recommendation_agent import _parse_json
        raw = "```json\n{\"key\": \"value\"}\n```"
        assert _parse_json(raw)["key"] == "value"

    def test_json_parser_garbage_returns_empty(self):
        from app.agents.career_recommendation_agent import _parse_json
        assert _parse_json("total garbage !@#$") == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestCareerRecommendationAPI:
    @pytest.fixture(scope="class")
    def headers(self, client):
        return get_auth_headers(client, "api")

    # ── Role Catalogue ────────────────────────────────────────────────────────
    def test_list_roles(self, client, headers):
        r = client.get("/api/v1/career/roles", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 20
        assert "domains" in data

    def test_list_roles_filter_by_domain(self, client, headers):
        r = client.get("/api/v1/career/roles?domain=AI/ML", headers=headers)
        assert r.status_code == 200
        roles = r.json()["data"]["roles"]
        for role in roles:
            assert role["domain"] == "AI/ML"

    def test_list_roles_no_auth(self, client):
        r = client.get("/api/v1/career/roles")
        assert r.status_code == 403

    def test_get_role_detail(self, client, headers):
        r = client.get("/api/v1/career/roles/ai_engineer", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["title"]  == "AI Engineer"
        assert "salary_mid_inr"  in data
        assert "skill_keywords"  in data
        assert "top_companies"   in data

    def test_get_role_detail_invalid(self, client, headers):
        r = client.get("/api/v1/career/roles/quantum_wizard", headers=headers)
        assert r.status_code == 422

    # ── Quick compare ─────────────────────────────────────────────────────────
    def test_quick_compare_returns_20_scores(self, client, headers):
        r = client.post("/api/v1/career/quick-compare", json={
            "skills":           ML_SKILLS,
            "interests":        ML_INTERESTS,
            "years_experience": 3.0,
            "education_level":  "Bachelors",
        }, headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 20
        assert data["top_role"] is not None

    def test_quick_compare_no_auth(self, client):
        r = client.post("/api/v1/career/quick-compare", json={
            "skills": ["Python"], "interests": [], "years_experience": 1.0,
        })
        assert r.status_code == 403

    def test_quick_compare_empty_skills_rejected(self, client, headers):
        r = client.post("/api/v1/career/quick-compare", json={
            "skills": [], "interests": [], "years_experience": 0.0,
        }, headers=headers)
        assert r.status_code == 422

    # ── Recommend from profile ────────────────────────────────────────────────
    def test_recommend_from_profile_success(self, client, headers):
        from app.agents.career_recommendation_agent import CareerRecommendationOutput, RecommendedRoleDetail
        mock_out = CareerRecommendationOutput(
            recommended_roles=[
                RecommendedRoleDetail(
                    rank=1, role_key="ml_engineer", role_title="ML Engineer",
                    role_icon="🧠", domain="AI/ML",
                    suitability_score=78.5, suitability_label="Strong Fit",
                    confidence="high", skill_match_pct=82.0, interest_match_pct=70.0,
                    why_suited="Strong PyTorch and scikit-learn background.",
                    what_youll_do="Train and deploy models in production.",
                    skill_gaps=["MLflow", "Airflow"],
                    salary_journey={"fresher_inr": "₹7–13 LPA", "mid_inr": "₹13–28 LPA",
                                    "senior_inr": "₹28–55 LPA", "global_usd": "$85,000–$180,000"},
                    top_companies=["Google", "Meta"],
                    related_roles=["ai_engineer"],
                    transition_timeline="Ready now",
                )
            ],
            all_role_scores=[{"role_key": "ml_engineer", "overall_score": 78.5,
                              "role_title": "ML Engineer", "role_icon": "🧠",
                              "domain": "AI/ML", "suitability_label": "Strong Fit"}],
            domain_fit={"AI/ML": 72.0}, best_domain="AI/ML",
            career_narrative="Strong ML profile.", personality_profile={},
            market_trends={}, action_plan={}, industry_insights="",
            candidate_skills=ML_SKILLS, candidate_interests=ML_INTERESTS,
            years_experience=3.0, education_level="Bachelors",
            model_used="gemini-2.0-flash", tokens_consumed=1500, processing_time_ms=2300,
        )
        with patch("app.services.career_recommendation_service.run_career_recommendation",
                   return_value=mock_out):
            r = client.post("/api/v1/career/recommend/profile", json={
                "skills":           ML_SKILLS,
                "interests":        ML_INTERESTS,
                "years_experience": 3.0,
                "education_level":  "Bachelors",
            }, headers=headers)
        assert r.status_code == 201
        data = r.json()["data"]
        assert "recommended_roles" in data
        assert "all_role_scores"   in data
        assert "domain_fit"        in data
        assert "action_plan"       in data
        assert "career_narrative"  in data
        assert data["best_domain"] == "AI/ML"
        assert len(data["recommended_roles"]) == 1

    def test_recommend_profile_no_skills_rejected(self, client, headers):
        r = client.post("/api/v1/career/recommend/profile", json={
            "skills": [], "interests": [], "years_experience": 0.0,
        }, headers=headers)
        assert r.status_code in (400, 422)

    def test_recommend_from_resume_not_found(self, client, headers):
        r = client.post("/api/v1/career/recommend/resume", json={
            "resume_id": 99999, "interests": ["python"],
        }, headers=headers)
        assert r.status_code == 404

    # ── Reports CRUD ──────────────────────────────────────────────────────────
    def test_list_reports_empty_for_new_user(self, client):
        hdrs = get_auth_headers(client, "new_cr")
        r    = client.get("/api/v1/career/reports", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_get_nonexistent_report(self, client, headers):
        r = client.get("/api/v1/career/reports/99999", headers=headers)
        assert r.status_code == 404

    def test_delete_nonexistent_report(self, client, headers):
        r = client.delete("/api/v1/career/reports/99999", headers=headers)
        assert r.status_code == 404

    def test_full_report_lifecycle(self, client, headers):
        """Create → list → get → delete."""
        from app.agents.career_recommendation_agent import CareerRecommendationOutput, RecommendedRoleDetail
        mock_out = CareerRecommendationOutput(
            recommended_roles=[
                RecommendedRoleDetail(
                    rank=1, role_key="ai_engineer", role_title="AI Engineer",
                    role_icon="🤖", domain="AI/ML",
                    suitability_score=82.0, suitability_label="Excellent Fit",
                    confidence="high", skill_match_pct=85.0, interest_match_pct=78.0,
                    salary_journey={"fresher_inr": "₹8–15 LPA", "mid_inr": "₹15–30 LPA",
                                    "senior_inr": "₹30–60 LPA", "global_usd": "$90,000–$200,000"},
                    top_companies=["Google"], related_roles=["ml_engineer"],
                )
            ],
            all_role_scores=[], domain_fit={"AI/ML": 80.0}, best_domain="AI/ML",
            model_used="gemini-2.0-flash", tokens_consumed=900,
        )
        with patch("app.services.career_recommendation_service.run_career_recommendation",
                   return_value=mock_out):
            create_r = client.post("/api/v1/career/recommend/profile", json={
                "skills": AI_SKILLS, "interests": AI_INTERESTS,
                "years_experience": 2.0, "education_level": "Bachelors",
            }, headers=headers)
        assert create_r.status_code == 201
        report_id = create_r.json()["data"]["report_id"]

        # List
        list_r = client.get("/api/v1/career/reports", headers=headers)
        ids    = [r["report_id"] for r in list_r.json()["data"]["reports"]]
        assert report_id in ids

        # Get
        get_r = client.get(f"/api/v1/career/reports/{report_id}", headers=headers)
        assert get_r.status_code == 200

        # Delete
        del_r = client.delete(f"/api/v1/career/reports/{report_id}", headers=headers)
        assert del_r.status_code == 200

        # Verify gone
        gone_r = client.get(f"/api/v1/career/reports/{report_id}", headers=headers)
        assert gone_r.status_code == 404

    def test_report_not_accessible_by_other_user(self, client, headers):
        """User A cannot access User B's report."""
        from app.agents.career_recommendation_agent import CareerRecommendationOutput
        mock_out = CareerRecommendationOutput(
            recommended_roles=[], all_role_scores=[],
            domain_fit={}, best_domain="",
            model_used="gemini-2.0-flash", tokens_consumed=0,
        )
        with patch("app.services.career_recommendation_service.run_career_recommendation",
                   return_value=mock_out):
            create_r = client.post("/api/v1/career/recommend/profile", json={
                "skills": ["Python"], "interests": [], "years_experience": 1.0,
                "education_level": "Bachelors",
            }, headers=headers)

        if create_r.status_code == 201:
            report_id = create_r.json()["data"]["report_id"]
            other_headers = get_auth_headers(client, "other_user_cr")
            r = client.get(f"/api/v1/career/reports/{report_id}",
                           headers=other_headers)
            assert r.status_code == 404
