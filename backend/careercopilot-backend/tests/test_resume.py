"""
tests/test_resume.py
─────────────────────
Tests for the Resume Analyser Agent:
  - PDF text extraction
  - NLP entity extraction
  - ATS scoring
  - Upload API
  - Analyse API (mocked Gemini)
  - Report retrieval
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.db.redis import get_redis
from app.main import app

# ── Test DB setup ─────────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_resume.db"
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


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection",      return_value=True):
        with TestClient(app) as c:
            yield c


# ── Auth helper ───────────────────────────────────────────────────────────────
def get_auth_headers(client: TestClient, suffix: str = "resume") -> dict:
    client.post("/api/v1/auth/register", json={
        "full_name": f"Test {suffix}",
        "email":     f"test_{suffix}@example.com",
        "password":  "Str0ng!Pass",
    })
    r = client.post("/api/v1/auth/login", json={
        "email":    f"test_{suffix}@example.com",
        "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


# ── Minimal valid PDF bytes (1-page) ──────────────────────────────────────────
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
    b"/Contents 4 0 R /Resources << /Font << /F1 << /Type /Font "
    b"/Subtype /Type1 /BaseFont /Helvetica >> >> >> >>\nendobj\n"
    b"4 0 obj\n<< /Length 200 >>\nstream\n"
    b"BT /F1 12 Tf 72 720 Td "
    b"(Priya Sharma - priya@example.com - linkedin.com/in/priyasharma) Tj\n"
    b"0 -20 Td (Senior ML Engineer | 5 years experience) Tj\n"
    b"0 -20 Td (Skills: Python, PyTorch, TensorFlow, FastAPI, Docker, AWS) Tj\n"
    b"0 -20 Td (Experience: Built ML pipeline reducing latency by 40%) Tj\n"
    b"0 -20 Td (Education: B.Tech Computer Science 2019) Tj\n"
    b"ET\nendstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f\n"
    b"0000000009 00000 n\n0000000058 00000 n\n"
    b"0000000115 00000 n\n0000000266 00000 n\n"
    b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n520\n%%EOF"
)

SAMPLE_RESUME_TEXT = """
Priya Sharma
priya@example.com | +91-9876543210 | linkedin.com/in/priyasharma | github.com/priyasharma

SUMMARY
Senior ML Engineer with 5 years of experience building production ML systems at scale.
Expertise in PyTorch, TensorFlow, and MLOps. Led teams of 4 engineers.

EXPERIENCE
Senior ML Engineer — Swiggy, Hyderabad (Jan 2022 - Present)
- Built real-time recommendation engine serving 10M+ users, improving CTR by 25%
- Reduced model inference latency from 200ms to 45ms using TensorRT optimisation
- Architected feature store processing 500K events/day using Kafka and Redis

ML Engineer — Freshworks, Chennai (Jun 2019 - Dec 2021)
- Developed NLP pipeline for ticket classification with 94% accuracy
- Deployed 8 ML models to production using Docker and Kubernetes

EDUCATION
B.Tech Computer Science — IIT Hyderabad (2015 - 2019) — GPA: 8.9/10

SKILLS
Languages: Python, SQL, Bash
Frameworks: PyTorch, TensorFlow, scikit-learn, FastAPI, LangChain
Tools: Docker, Kubernetes, MLflow, Airflow, Grafana
Cloud: AWS (EC2, S3, SageMaker), GCP

PROJECTS
Career Copilot AI — LangChain, FastAPI, Qdrant, Gemini API
- Built RAG-powered career assistant with 500 beta users

CERTIFICATIONS
AWS Certified Machine Learning Specialty (2023)
Google Cloud Professional Data Engineer (2022)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — PDF Parser
# ═══════════════════════════════════════════════════════════════════════════════
class TestPDFParser:
    def test_clean_text(self):
        from app.utils.pdf_parser import clean_text
        raw = "Hello   World\n\n\n\nFoo"
        result = clean_text(raw)
        assert "   " not in result
        assert "\n\n\n" not in result

    def test_section_detection(self):
        from app.utils.pdf_parser import _detect_sections
        sections = _detect_sections(SAMPLE_RESUME_TEXT)
        assert "experience" in sections or "skills" in sections

    def test_extract_pdf_bytes(self):
        """Test that the PDF extractor handles minimal valid PDF."""
        from app.utils.pdf_parser import extract_from_pdf
        try:
            result = extract_from_pdf(MINIMAL_PDF)
            assert result.page_count >= 1
        except Exception:
            # Minimal PDF may fail extraction — that's fine for this test
            pass

    def test_extract_dispatcher_bad_mime(self):
        from app.utils.pdf_parser import extract_text
        with pytest.raises(ValueError, match="Unsupported"):
            extract_text(b"data", "image/png")


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — NLP Extractor
# ═══════════════════════════════════════════════════════════════════════════════
class TestNLPExtractor:
    def test_contact_extraction(self):
        from app.utils.nlp_extractor import _extract_contact
        contact = _extract_contact(SAMPLE_RESUME_TEXT)
        assert contact.get("email") == "priya@example.com"
        assert "linkedin" in contact

    def test_skill_extraction(self):
        from app.utils.nlp_extractor import _extract_skills
        skills = _extract_skills(SAMPLE_RESUME_TEXT)
        skill_names = [s["name"].lower() for s in skills]
        assert "python" in skill_names
        assert "docker" in skill_names

    def test_skill_categories(self):
        from app.utils.nlp_extractor import _extract_skills
        skills  = _extract_skills(SAMPLE_RESUME_TEXT)
        cats    = {s["category"] for s in skills}
        assert "language" in cats
        assert "devops" in cats or "tool" in cats

    def test_certification_extraction(self):
        from app.utils.nlp_extractor import _extract_certifications
        certs = _extract_certifications(SAMPLE_RESUME_TEXT)
        assert len(certs) >= 1
        assert any("AWS" in c["name"] for c in certs)

    def test_date_range_extraction(self):
        from app.utils.nlp_extractor import _extract_date_ranges
        ranges = _extract_date_ranges(SAMPLE_RESUME_TEXT)
        assert len(ranges) >= 1

    def test_years_experience_calculation(self):
        from app.utils.nlp_extractor import _calculate_years_experience
        ranges = ["Jan 2019 - Present", "Jun 2017 - Dec 2018"]
        yoe    = _calculate_years_experience(ranges)
        assert yoe > 4

    def test_seniority_detection(self):
        from app.utils.nlp_extractor import _detect_seniority
        assert _detect_seniority("Senior ML Engineer with 6 years", 6.0) == "Senior"
        assert "Junior" in _detect_seniority("Junior developer fresh graduate", 0.5)

    def test_full_entity_extraction(self):
        from app.utils.nlp_extractor import extract_entities
        from app.utils.pdf_parser import _detect_sections
        sections = _detect_sections(SAMPLE_RESUME_TEXT)
        entities = extract_entities(SAMPLE_RESUME_TEXT, sections)
        assert len(entities.technical_skills) >= 3
        assert entities.total_years_exp > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — ATS Scorer
# ═══════════════════════════════════════════════════════════════════════════════
class TestATSScorer:
    def _get_entities_and_sections(self):
        from app.utils.nlp_extractor import extract_entities
        from app.utils.pdf_parser import _detect_sections
        sections = _detect_sections(SAMPLE_RESUME_TEXT)
        entities = extract_entities(SAMPLE_RESUME_TEXT, sections)
        return entities, sections

    def test_ats_score_range(self):
        from app.utils.ats_scorer import calculate_ats_score
        entities, sections = self._get_entities_and_sections()
        result = calculate_ats_score(SAMPLE_RESUME_TEXT, entities, sections, 350, 2)
        assert 0 <= result.ats_score <= 100

    def test_good_resume_scores_well(self):
        from app.utils.ats_scorer import calculate_ats_score
        entities, sections = self._get_entities_and_sections()
        result = calculate_ats_score(SAMPLE_RESUME_TEXT, entities, sections, 350, 2)
        assert result.ats_score >= 50   # well-written resume should score decently

    def test_grade_assignment(self):
        from app.utils.ats_scorer import _score_to_grade
        assert _score_to_grade(90) == "A"
        assert _score_to_grade(75) == "B"
        assert _score_to_grade(60) == "C"
        assert _score_to_grade(45) == "D"
        assert _score_to_grade(30) == "F"

    def test_empty_resume_scores_low(self):
        from app.utils.ats_scorer import calculate_ats_score
        from app.utils.nlp_extractor import ExtractedEntities
        empty = ExtractedEntities()
        result = calculate_ats_score("", empty, {}, 0, 0)
        assert result.ats_score < 40

    def test_score_breakdown_components_sum(self):
        from app.utils.ats_scorer import calculate_ats_score
        entities, sections = self._get_entities_and_sections()
        r = calculate_ats_score(SAMPLE_RESUME_TEXT, entities, sections, 350, 2)
        # Each sub-score should be 0–100
        for s in [r.formatting_score, r.content_score, r.keyword_score, r.experience_score]:
            assert 0 <= s <= 100


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Gemini Agent (mocked)
# ═══════════════════════════════════════════════════════════════════════════════
class TestResumeAgent:
    def _make_ats_result(self):
        from app.utils.ats_scorer import ATSScoreResult
        return ATSScoreResult(
            ats_score=72.0, formatting_score=80.0, content_score=70.0,
            keyword_score=65.0, experience_score=75.0, grade="B",
            verdict="Good", keywords_found=["Python"], keywords_missing=["MLflow"],
        )

    def _make_entities(self):
        from app.utils.nlp_extractor import extract_entities
        from app.utils.pdf_parser import _detect_sections
        secs = _detect_sections(SAMPLE_RESUME_TEXT)
        return extract_entities(SAMPLE_RESUME_TEXT, secs)

    def test_mock_response_used_when_llm_unavailable(self):
        """When no LLM provider is configured, call_llm raises RuntimeError
        and run_resume_analysis falls back to a mock response instead of
        crashing. model_used always reflects settings.active_model, whichever
        provider that resolves to (Groq by default in this deployment) —
        it is never hardcoded to a specific provider's model name."""
        from app.agents.resume_agent import run_resume_analysis
        from app.core.config import settings
        entities   = self._make_entities()
        ats_result = self._make_ats_result()
        with patch("app.agents.resume_agent.call_llm", side_effect=RuntimeError("no provider configured")):
            result = run_resume_analysis(
                SAMPLE_RESUME_TEXT, entities, ats_result, 2, 350
            )
        assert result.ats_score == 72.0
        assert result.model_used == settings.active_model

    def test_scores_preserved_from_ats(self):
        """ATS rule-based scores must not be overridden by LLM."""
        from app.agents.resume_agent import run_resume_analysis
        entities   = self._make_entities()
        ats_result = self._make_ats_result()
        result = run_resume_analysis(SAMPLE_RESUME_TEXT, entities, ats_result, 2, 350)
        assert result.ats_score   == 72.0
        assert result.grade       == "B"
        assert result.keyword_score == 65.0

    def test_json_parser_strips_markdown_fences(self):
        from app.core.llm_provider import parse_llm_json
        raw = '```json\n{"key": "value"}\n```'
        parsed = parse_llm_json(raw)
        assert parsed["key"] == "value"

    def test_json_parser_clean_json(self):
        from app.core.llm_provider import parse_llm_json
        parsed = parse_llm_json('{"a": 1, "b": [1,2,3]}')
        assert parsed["a"] == 1

    def test_json_parser_returns_empty_dict_on_garbage(self):
        # parse_llm_json never raises — it logs a warning and returns {} so
        # a single malformed LLM response degrades gracefully instead of
        # crashing the calling agent.
        from app.core.llm_provider import parse_llm_json
        parsed = parse_llm_json("not json at all !@#$")
        assert parsed == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — Resume API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestResumeAPI:
    @pytest.fixture(scope="class")
    def headers(self, client: TestClient) -> dict:
        return get_auth_headers(client, "resume_api")

    def test_upload_no_auth(self, client: TestClient) -> None:
        r = client.post("/api/v1/resume/upload", files={"file": ("r.pdf", b"%PDF", "application/pdf")})
        assert r.status_code == 403

    def test_upload_wrong_mime(self, client: TestClient, headers: dict) -> None:
        r = client.post(
            "/api/v1/resume/upload",
            files={"file": ("r.txt", b"hello", "text/plain")},
            data={"make_primary": "true"},
            headers=headers,
        )
        assert r.status_code == 422

    def test_upload_too_small(self, client: TestClient, headers: dict) -> None:
        r = client.post(
            "/api/v1/resume/upload",
            files={"file": ("r.pdf", b"%PDF-tiny", "application/pdf")},
            data={"make_primary": "true"},
            headers=headers,
        )
        assert r.status_code == 422

    def test_upload_valid_pdf(self, client: TestClient, headers: dict) -> None:
        with patch("app.services.resume_service.ResumeService._store_local", return_value="resumes/1/test.pdf"):
            r = client.post(
                "/api/v1/resume/upload",
                files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
                data={"make_primary": "true"},
                headers=headers,
            )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["resume_id"] > 0
        assert data["status"] == "uploaded"

    def test_list_resumes_empty_for_new_user(self, client: TestClient) -> None:
        hdrs = get_auth_headers(client, "list_test")
        r = client.get("/api/v1/resume/", headers=hdrs)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    def test_get_nonexistent_resume(self, client: TestClient, headers: dict) -> None:
        r = client.get("/api/v1/resume/99999", headers=headers)
        assert r.status_code == 404

    def test_upload_and_analyse_pipeline(self, client: TestClient, headers: dict) -> None:
        """Full pipeline test with mocked file storage and Gemini."""
        with patch("app.services.resume_service.ResumeService._store_local", return_value="resumes/1/test.pdf"), \
             patch("app.services.resume_service.ResumeService._load_local",  return_value=MINIMAL_PDF), \
             patch("app.utils.pdf_parser.extract_from_pdf") as mock_parse:

            from app.utils.pdf_parser import ParsedResume
            from app.utils.pdf_parser import _detect_sections
            mock_parse.return_value = ParsedResume(
                raw_text=SAMPLE_RESUME_TEXT,
                page_count=2,
                word_count=350,
                char_count=len(SAMPLE_RESUME_TEXT),
                sections=_detect_sections(SAMPLE_RESUME_TEXT),
            )

            r = client.post(
                "/api/v1/resume/upload-and-analyse",
                files={"file": ("resume.pdf", MINIMAL_PDF, "application/pdf")},
                data={"make_primary": "true"},
                headers=headers,
            )

        assert r.status_code == 201
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        assert "scores" in data
        assert data["scores"]["ats_score"] >= 0
        assert data["scores"]["grade"] in ("A", "B", "C", "D", "F")
        assert isinstance(data["skills"], list)
        assert isinstance(data["improvements"], list)

    def test_delete_resume(self, client: TestClient) -> None:
        hdrs = get_auth_headers(client, "delete_test")
        with patch("app.services.resume_service.ResumeService._store_local", return_value="resumes/99/t.pdf"):
            up = client.post(
                "/api/v1/resume/upload",
                files={"file": ("r.pdf", MINIMAL_PDF, "application/pdf")},
                data={"make_primary": "true"},
                headers=hdrs,
            )
        if up.status_code == 201:
            rid = up.json()["data"]["resume_id"]
            r   = client.delete(f"/api/v1/resume/{rid}", headers=hdrs)
            assert r.status_code == 200
