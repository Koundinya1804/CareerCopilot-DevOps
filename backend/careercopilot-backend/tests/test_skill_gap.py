"""
tests/test_skill_gap.py
────────────────────────
Tests for the Skill Gap Analyzer Agent:

  Unit:
    - Role skill DB (registry, lookups, role definitions)
    - Skill matcher (exact, alias, partial, scoring, severity)
    - Agent pipeline (mock Gemini, JSON parsing)

  Integration:
    - API endpoints (analyse, compare, list, CRUD)
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
TEST_DB_URL = "sqlite:///./test_skill_gap.db"
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
    Path("test_skill_gap.db").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection",      return_value=True):
        with TestClient(app) as c:
            yield c


def get_auth_headers(client, suffix="sg"):
    client.post("/api/v1/auth/register", json={
        "full_name": f"SG User {suffix}", "email": f"sg_{suffix}@test.com",
        "password": "Str0ng!Pass",
    })
    r = client.post("/api/v1/auth/login", json={
        "email": f"sg_{suffix}@test.com", "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


SAMPLE_RESUME = """
Priya Sharma — Senior ML Engineer
priya@example.com | github.com/priyasharma | linkedin.com/in/priyasharma

SKILLS
Python, PyTorch, scikit-learn, NumPy, Pandas, FastAPI, Docker, Git, SQL, Linux

EXPERIENCE
ML Engineer — Swiggy (Jan 2022 - Present)
- Built recommendation engine using PyTorch, improved CTR by 25%
- Deployed models with Docker and Kubernetes
- Used MLflow for experiment tracking

EDUCATION
B.Tech Computer Science — IIT Hyderabad 2019

PROJECTS
RAG-based Career Assistant — LangChain, FastAPI, ChromaDB, Gemini API
- Built RAG pipeline with 500 beta users
"""

AI_ENGINEER_RESUME = """
DevOps Engineer with cloud expertise
Skills: AWS, GCP, Terraform, Docker, Kubernetes, Python, Bash, CI/CD, GitHub Actions
Jenkins, Prometheus, Grafana, Linux, Helm, S3, IAM, Networking, Load Balancing
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Role Skill Database
# ═══════════════════════════════════════════════════════════════════════════════
class TestRoleSkillDB:
    def test_six_roles_defined(self):
        from app.agents.role_skill_db import ROLE_REGISTRY
        assert len(ROLE_REGISTRY) == 6
        expected = {"ai_engineer","ml_engineer","data_scientist",
                    "java_developer","fullstack_developer","cloud_engineer"}
        assert set(ROLE_REGISTRY.keys()) == expected

    def test_get_role_valid(self):
        from app.agents.role_skill_db import get_role
        r = get_role("ml_engineer")
        assert r.title == "ML Engineer"
        assert len(r.required_skills) > 0
        assert len(r.preferred_skills) > 0

    def test_get_role_invalid(self):
        from app.agents.role_skill_db import get_role
        with pytest.raises(ValueError, match="Unknown role"):
            get_role("blockchain_engineer")

    def test_every_role_has_critical_skills(self):
        from app.agents.role_skill_db import ROLE_REGISTRY, Priority
        for key, role in ROLE_REGISTRY.items():
            critical = [s for s in role.required_skills if s.priority == Priority.CRITICAL]
            assert len(critical) >= 1, f"{key} has no critical skills"

    def test_salary_ranges_sensible(self):
        from app.agents.role_skill_db import ROLE_REGISTRY
        for key, role in ROLE_REGISTRY.items():
            lo, hi = role.salary_range_inr
            assert lo > 0 and hi > lo, f"{key} salary range invalid"

    def test_ai_engineer_requires_llm(self):
        from app.agents.role_skill_db import get_role
        r     = get_role("ai_engineer")
        names = [s.name.lower() for s in r.required_skills]
        assert any("llm" in n or "language model" in n for n in names)

    def test_cloud_engineer_requires_terraform(self):
        from app.agents.role_skill_db import get_role
        r     = get_role("cloud_engineer")
        names = [s.name.lower() for s in r.required_skills]
        assert any("terraform" in n for n in names)

    def test_get_skill_names(self):
        from app.agents.role_skill_db import get_skill_names
        names = get_skill_names("python_developer" if "python_developer" in
                                __import__("app.agents.role_skill_db",
                                           fromlist=["ROLE_REGISTRY"]).ROLE_REGISTRY
                                else "ml_engineer")
        assert isinstance(names, set)
        assert len(names) > 5


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Skill Matcher
# ═══════════════════════════════════════════════════════════════════════════════
class TestSkillMatcher:
    def test_exact_match(self):
        from app.agents.skill_matcher import match_skills
        r = match_skills(["Python", "Docker", "Git", "SQL", "FastAPI",
                          "REST API Design", "Linux / Bash"], "ml_engineer")
        assert r.required_match_pct > 0
        matched_names = [m.role_skill_name for m in r.matched]
        assert any("Python" in n for n in matched_names)

    def test_alias_match_torch(self):
        from app.agents.skill_matcher import _names_match
        assert _names_match("torch", "PyTorch") is True
        assert _names_match("pytorch", "PyTorch") is True

    def test_alias_match_sklearn(self):
        from app.agents.skill_matcher import _names_match
        assert _names_match("sklearn", "scikit-learn") is True
        assert _names_match("scikit learn", "scikit-learn") is True

    def test_alias_match_langchain(self):
        from app.agents.skill_matcher import _names_match
        assert _names_match("LangChain", "LangChain / LangGraph") is True

    def test_alias_match_aws(self):
        from app.agents.skill_matcher import _names_match
        assert _names_match("AWS", "AWS / GCP / Azure") is True
        assert _names_match("GCP", "AWS / GCP / Azure") is True

    def test_no_match_unrelated(self):
        from app.agents.skill_matcher import _names_match
        assert _names_match("photoshop", "Python") is False
        assert _names_match("cooking", "Docker") is False

    def test_full_ml_engineer_match(self):
        from app.agents.skill_matcher import match_skills
        skills = ["Python", "PyTorch", "scikit-learn", "NumPy", "Pandas",
                  "Docker", "Git", "SQL", "MLflow", "Statistics",
                  "Machine Learning", "Deep Learning", "FastAPI"]
        r = match_skills(skills, "ml_engineer")
        assert r.overall_match_pct > 50
        assert r.required_match_pct > 50

    def test_zero_skills_gives_zero_match(self):
        from app.agents.skill_matcher import match_skills
        r = match_skills([], "ml_engineer")
        assert r.overall_match_pct == 0.0
        assert r.required_match_pct == 0.0

    def test_gap_severity_levels(self):
        from app.agents.skill_matcher import match_skills
        # Perfect match → none/minor
        all_skills = [
            "Python", "PyTorch", "TensorFlow", "scikit-learn", "NumPy", "Pandas",
            "Docker", "Git", "SQL", "MLflow", "Statistics", "Deep Learning",
            "Machine Learning", "Feature Engineering", "REST API", "Linux",
            "NLP", "Kubernetes", "Apache Spark", "Airflow",
        ]
        r = match_skills(all_skills, "ml_engineer")
        assert r.gap_severity in ("none", "minor", "moderate")

        # No skills → critical
        r2 = match_skills([], "ml_engineer")
        assert r2.gap_severity == "critical"

    def test_cloud_engineer_match(self):
        from app.agents.skill_matcher import match_skills
        skills = ["AWS", "Terraform", "Docker", "Kubernetes", "Linux",
                  "Python", "Git", "GitHub Actions", "Prometheus", "S3"]
        r = match_skills(skills, "cloud_engineer")
        assert r.required_match_pct > 50

    def test_preferred_skills_not_required(self):
        from app.agents.skill_matcher import match_skills
        # Only provide required skills, no preferred
        r = match_skills(["Python", "PyTorch", "scikit-learn", "NumPy",
                          "Docker", "Git", "SQL", "MLflow"], "ml_engineer")
        # Preferred match should be low
        assert r.preferred_match_pct < r.required_match_pct

    def test_extract_skills_from_text(self):
        from app.agents.skill_matcher import extract_skills_from_text
        skills = extract_skills_from_text(SAMPLE_RESUME)
        assert isinstance(skills, list)
        assert len(skills) > 0
        skill_names_lower = [s.lower() for s in skills]
        assert any("python" in s for s in skill_names_lower)

    def test_estimated_prep_months_increases_with_gap(self):
        from app.agents.skill_matcher import match_skills
        r_good = match_skills(
            ["Python","PyTorch","scikit-learn","Docker","Git","SQL","MLflow","NumPy","Pandas"],
            "ml_engineer"
        )
        r_poor = match_skills([], "ml_engineer")
        assert r_poor.estimated_prep_months > r_good.estimated_prep_months


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Skill Gap Agent (mock Gemini)
# ═══════════════════════════════════════════════════════════════════════════════
class TestSkillGapAgent:
    def test_mock_mode_when_no_key(self):
        from app.agents.skill_gap_agent import run_skill_gap_analysis
        result = run_skill_gap_analysis(SAMPLE_RESUME, "ml_engineer")
        assert result.role_key    == "ml_engineer"
        assert result.role_title  == "ML Engineer"
        assert result.overall_match_pct >= 0
        assert result.model_used  == "gemini-2.0-flash"

    def test_scores_are_deterministic(self):
        from app.agents.skill_gap_agent import run_skill_gap_analysis
        r1 = run_skill_gap_analysis(SAMPLE_RESUME, "ml_engineer")
        r2 = run_skill_gap_analysis(SAMPLE_RESUME, "ml_engineer")
        assert r1.overall_match_pct   == r2.overall_match_pct
        assert r1.required_match_pct  == r2.required_match_pct

    def test_all_roles_run(self):
        from app.agents.skill_gap_agent import run_skill_gap_analysis
        from app.agents.role_skill_db import ROLE_REGISTRY
        for key in ROLE_REGISTRY:
            r = run_skill_gap_analysis(SAMPLE_RESUME, key)
            assert r.role_key == key
            assert 0 <= r.overall_match_pct <= 100

    def test_json_parser_handles_markdown_fences(self):
        from app.agents.skill_gap_agent import _parse_json
        raw = '```json\n{"executive_summary": "test"}\n```'
        out = _parse_json(raw)
        assert out["executive_summary"] == "test"

    def test_json_parser_clean_json(self):
        from app.agents.skill_gap_agent import _parse_json
        out = _parse_json('{"a": 1, "b": [1,2,3]}')
        assert out["a"] == 1

    def test_json_parser_returns_empty_on_garbage(self):
        from app.agents.skill_gap_agent import _parse_json
        out = _parse_json("complete garbage !@#$")
        assert out == {}

    def test_extra_skills_merged(self):
        from app.agents.skill_gap_agent import run_skill_gap_analysis
        r_without = run_skill_gap_analysis("Python developer", "ml_engineer")
        r_with    = run_skill_gap_analysis("Python developer", "ml_engineer",
                                           extra_skills=["PyTorch", "scikit-learn",
                                                         "NumPy", "MLflow"])
        assert r_with.overall_match_pct >= r_without.overall_match_pct

    def test_ai_engineer_rag_resume_scores_well(self):
        from app.agents.skill_gap_agent import run_skill_gap_analysis
        ai_resume = """
        AI Engineer with expertise in LangChain, LangGraph, RAG pipelines,
        LLMs, Gemini API, FastAPI, ChromaDB, Vector Databases, Embeddings,
        Semantic Search, Prompt Engineering, Python, Docker, Git, SQL, Async Python.
        """
        r = run_skill_gap_analysis(ai_resume, "ai_engineer")
        assert r.required_match_pct > 50


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Schemas
# ═══════════════════════════════════════════════════════════════════════════════
class TestSchemas:
    def test_score_to_grade(self):
        from app.schemas.skill_gap import score_to_grade
        assert score_to_grade(90) == "A"
        assert score_to_grade(75) == "B"
        assert score_to_grade(60) == "C"
        assert score_to_grade(45) == "D"
        assert score_to_grade(20) == "F"

    def test_score_to_readiness(self):
        from app.schemas.skill_gap import score_to_readiness
        assert "Ready"     in score_to_readiness(92)
        assert "Confident" in score_to_readiness(72)
        assert "Short"     in score_to_readiness(58)
        assert "Focused"   in score_to_readiness(42)
        assert "Significant" in score_to_readiness(20)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestSkillGapAPI:
    @pytest.fixture(scope="class")
    def headers(self, client):
        return get_auth_headers(client, "api")

    # ── Role catalogue ────────────────────────────────────────────────────────
    def test_list_roles(self, client, headers):
        r = client.get("/api/v1/skill-gap/roles", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 6
        keys = [ro["key"] for ro in data["roles"]]
        assert "ai_engineer"    in keys
        assert "cloud_engineer" in keys

    def test_list_roles_no_auth(self, client):
        r = client.get("/api/v1/skill-gap/roles")
        assert r.status_code == 403

    def test_get_role_detail(self, client, headers):
        r = client.get("/api/v1/skill-gap/roles/ml_engineer", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["title"] == "ML Engineer"
        assert len(data["required_skills"]) > 0
        assert "certifications" in data
        assert "career_path"    in data

    def test_get_role_invalid(self, client, headers):
        r = client.get("/api/v1/skill-gap/roles/blockchain_dev", headers=headers)
        assert r.status_code == 422

    # ── Analyse from text ─────────────────────────────────────────────────────
    def test_analyse_from_text_success(self, client, headers):
        from app.agents.skill_gap_agent import SkillGapAnalysisResult
        mock_result = SkillGapAnalysisResult(
            role_key="ml_engineer", role_title="ML Engineer",
            overall_match_pct=68.5, required_match_pct=72.0, preferred_match_pct=58.0,
            gap_severity="moderate", estimated_prep_months=4,
            matched_skills=[{"name":"Python","priority":"critical"}],
            missing_required=[{"name":"MLflow","priority":"high"}],
            missing_preferred=[],
            executive_summary="Strong ML foundation. Close to role readiness.",
            detailed_feedback="Focus on MLOps tooling.",
            strengths=["Strong Python skills"],
            learning_priorities=[{"rank":1,"skill":"MLflow","why":"MLOps","time_weeks":3,"approach":"Build a project"}],
            recommended_courses=[{"title":"MLOps Course","platform":"Coursera","url":"","skill_covered":"MLflow","duration_weeks":4,"is_free":False,"priority":"high"}],
            recommended_projects=[],
            recommended_certs=[],
            quick_wins=[{"action":"Add MLflow to resume","impact":"Shows awareness","time_days":1}],
            salary_insight="Can target ₹10-18 LPA now.",
            model_used="gemini-2.0-flash", tokens_consumed=1200, processing_time_ms=2100,
        )
        with patch("app.services.skill_gap_service.run_skill_gap_analysis",
                   return_value=mock_result):
            r = client.post("/api/v1/skill-gap/analyse/text", json={
                "resume_text": SAMPLE_RESUME,
                "role_key":    "ml_engineer",
            }, headers=headers)
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["role_key"]                   == "ml_engineer"
        assert data["scores"]["overall_match_pct"] == 68.5
        assert data["scores"]["grade"]            == "C"
        assert "readiness_label"     in data["scores"]
        assert "executive_summary"   in data
        assert "learning_priorities" in data
        assert "recommended_courses" in data
        assert "quick_wins"          in data

    def test_analyse_text_too_short(self, client, headers):
        r = client.post("/api/v1/skill-gap/analyse/text",
                        json={"resume_text": "Hi", "role_key": "ml_engineer"},
                        headers=headers)
        assert r.status_code == 422

    def test_analyse_text_invalid_role(self, client, headers):
        with patch("app.services.skill_gap_service.run_skill_gap_analysis") as mock_fn:
            mock_fn.side_effect = ValueError("Unknown role 'blockchain'")
            r = client.post("/api/v1/skill-gap/analyse/text", json={
                "resume_text": SAMPLE_RESUME, "role_key": "blockchain",
            }, headers=headers)
        assert r.status_code in (422, 500)

    def test_analyse_no_auth(self, client):
        r = client.post("/api/v1/skill-gap/analyse/text",
                        json={"resume_text": SAMPLE_RESUME, "role_key": "ml_engineer"})
        assert r.status_code == 403

    # ── Compare roles ─────────────────────────────────────────────────────────
    def test_compare_roles_requires_resume(self, client, headers):
        r = client.post("/api/v1/skill-gap/compare", json={
            "resume_id": 99999, "role_keys": ["ml_engineer", "data_scientist"],
        }, headers=headers)
        # 404 — resume doesn't exist
        assert r.status_code == 404

    def test_compare_requires_2_roles_minimum(self, client, headers):
        r = client.post("/api/v1/skill-gap/compare",
                        json={"resume_id": 1, "role_keys": ["ml_engineer"]},
                        headers=headers)
        assert r.status_code == 422

    # ── List / CRUD reports ───────────────────────────────────────────────────
    def test_list_reports_empty(self, client):
        hdrs = get_auth_headers(client, "listreports")
        r = client.get("/api/v1/skill-gap/reports", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_get_nonexistent_report(self, client, headers):
        r = client.get("/api/v1/skill-gap/reports/99999", headers=headers)
        assert r.status_code == 404

    def test_delete_nonexistent_report(self, client, headers):
        r = client.delete("/api/v1/skill-gap/reports/99999", headers=headers)
        assert r.status_code == 404

    def test_full_lifecycle(self, client, headers):
        """Create report via text → list → get → delete."""
        from app.agents.skill_gap_agent import SkillGapAnalysisResult
        mock_result = SkillGapAnalysisResult(
            role_key="ai_engineer", role_title="AI Engineer",
            overall_match_pct=55.0, required_match_pct=60.0, preferred_match_pct=40.0,
            gap_severity="moderate", estimated_prep_months=4,
            model_used="gemini-2.0-flash", tokens_consumed=800,
        )
        with patch("app.services.skill_gap_service.run_skill_gap_analysis",
                   return_value=mock_result):
            create_r = client.post("/api/v1/skill-gap/analyse/text", json={
                "resume_text": SAMPLE_RESUME,
                "role_key":    "ai_engineer",
            }, headers=headers)
        assert create_r.status_code == 201
        report_id = create_r.json()["data"]["gap_report_id"]

        # List
        list_r = client.get("/api/v1/skill-gap/reports", headers=headers)
        assert any(r["gap_report_id"] == report_id
                   for r in list_r.json()["data"]["reports"])

        # Get
        get_r = client.get(f"/api/v1/skill-gap/reports/{report_id}", headers=headers)
        assert get_r.status_code == 200
        assert get_r.json()["data"]["role_key"] == "ai_engineer"

        # Delete
        del_r = client.delete(f"/api/v1/skill-gap/reports/{report_id}", headers=headers)
        assert del_r.status_code == 200

        # Verify deleted
        gone_r = client.get(f"/api/v1/skill-gap/reports/{report_id}", headers=headers)
        assert gone_r.status_code == 404

    def test_filter_reports_by_role(self, client, headers):
        r = client.get("/api/v1/skill-gap/reports?role_key=ml_engineer",
                       headers=headers)
        assert r.status_code == 200
        reports = r.json()["data"]["reports"]
        for rep in reports:
            assert rep["role_key"] == "ml_engineer"
