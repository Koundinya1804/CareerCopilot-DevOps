"""
tests/test_interview.py
────────────────────────
Tests for the Interview Coach Agent:

  Unit:
    - Evaluator (confidence, technical, communication, relevance, completeness)
    - Question generation (fallback, all modes)
    - Report generation

  Integration:
    - Full session lifecycle (start → answer → complete → report)
    - All API endpoints
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
TEST_DB_URL = "sqlite:///./test_interview.db"
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
    Path("test_interview.db").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection",      return_value=True):
        with TestClient(app) as c:
            yield c


def get_auth_headers(client, suffix="iv"):
    client.post("/api/v1/auth/register", json={
        "full_name": f"Interview User {suffix}",
        "email":     f"iv_{suffix}@test.com",
        "password":  "Str0ng!Pass",
    })
    r = client.post("/api/v1/auth/login", json={
        "email": f"iv_{suffix}@test.com", "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


# ── Sample answers ─────────────────────────────────────────────────────────────
GOOD_BEHAVIOURAL = """
During my internship at Swiggy, our team faced a critical situation where our 
recommendation engine was returning irrelevant results, causing a 15% drop in CTR. 
My task was to debug and fix the pipeline within 48 hours before the product launch.

I approached this systematically: first I analyzed the data pipeline logs and 
discovered a data schema mismatch after a recent migration. I implemented a fix, 
added data validation tests, and deployed to staging. I then A/B tested the fix 
against the baseline, achieving a 20% CTR improvement over the original.

As a result, we launched on schedule and the feature delivered a 25% increase 
in order conversions in the first week. I also documented the root cause and 
added monitoring alerts to prevent similar issues.
"""

GOOD_TECHNICAL = """
A hash table is a data structure that maps keys to values using a hash function.
The hash function computes an index in an array where the value is stored.

Time complexity: O(1) average for insert, search, delete. O(n) worst case 
when many collisions occur.

Collision handling strategies:
1. Chaining: Each bucket stores a linked list. Simple but extra memory.
2. Open addressing: Linear probing, quadratic probing, double hashing.

Real-world usage: Python dictionaries, database indexes, caching (Redis).
I used hash tables to implement an LRU cache in production, 
combining a HashMap and doubly-linked list for O(1) operations.
"""

SHORT_ANSWER = "I don't know."

WEAK_ANSWER = "I think maybe I worked on a project once, kind of related to this I guess."


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Evaluator
# ═══════════════════════════════════════════════════════════════════════════════
class TestEvaluator:
    def test_good_behavioural_scores_well(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer(
            "Tell me about a challenge you overcame.",
            GOOD_BEHAVIOURAL, "behavioural"
        )
        assert result.overall_score > 50
        assert result.word_count > 80

    def test_good_technical_scores_well(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer(
            "What is a hash table?",
            GOOD_TECHNICAL, "technical", topic="data_structures"
        )
        assert result.overall_score > 50
        assert result.technical_score > 40

    def test_short_answer_scores_low(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer("Tell me about yourself.", SHORT_ANSWER, "hr")
        assert result.overall_score < 40

    def test_weak_answer_confidence_low(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer("Describe your strength.", WEAK_ANSWER, "hr")
        assert result.confidence_score < 50

    def test_empty_answer_returns_zeros(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer("Any question", "", "hr")
        assert result.overall_score == 0

    def test_star_breakdown_populated_for_behavioural(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer(
            "Tell me about a challenge.", GOOD_BEHAVIOURAL, "behavioural"
        )
        assert isinstance(result.star_breakdown, dict)

    def test_metrics_detected(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer(
            "Tell me about an achievement.",
            "I improved performance by 40% and reduced latency from 200ms to 45ms.",
            "behavioural"
        )
        assert result.has_metrics is True

    def test_technical_hr_returns_neutral_technical_score(self):
        from app.agents.interview_evaluator import evaluate_answer
        result = evaluate_answer(
            "Tell me about yourself.", "I am a software engineer with 3 years of experience.", "hr"
        )
        assert result.technical_score == 70.0   # neutral for HR

    def test_scores_in_valid_range(self):
        from app.agents.interview_evaluator import evaluate_answer
        for ans in [GOOD_BEHAVIOURAL, GOOD_TECHNICAL, SHORT_ANSWER, WEAK_ANSWER]:
            r = evaluate_answer("Question?", ans, "technical")
            assert 0 <= r.overall_score       <= 100
            assert 0 <= r.confidence_score    <= 100
            assert 0 <= r.technical_score     <= 100
            assert 0 <= r.communication_score <= 100
            assert 0 <= r.relevance_score     <= 100

    def test_long_answer_communication_not_penalised_badly(self):
        from app.agents.interview_evaluator import evaluate_answer
        long_answer = GOOD_BEHAVIOURAL * 2
        result = evaluate_answer("Tell me about a project.", long_answer, "behavioural")
        assert result.communication_score > 20


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Question Generation (fallback)
# ═══════════════════════════════════════════════════════════════════════════════
class TestQuestionGeneration:
    def test_fallback_hr_generates_n_questions(self):
        from app.agents.interview_coach_agent import _fallback_questions
        qs = _fallback_questions("hr", 5, "ML Engineer", "medium")
        assert len(qs) == 5
        for q in qs:
            assert q.question_text
            assert q.question_type

    def test_fallback_technical_generates_n_questions(self):
        from app.agents.interview_coach_agent import _fallback_questions
        qs = _fallback_questions("technical", 4, "Backend Engineer", "hard")
        assert len(qs) == 4

    def test_fallback_company_specific(self):
        from app.agents.interview_coach_agent import _fallback_questions
        qs = _fallback_questions("company_specific", 3, "SWE", "medium")
        assert len(qs) == 3

    def test_generate_questions_returns_list(self):
        from app.agents.interview_coach_agent import generate_questions
        qs = generate_questions("hr", 3, "ML Engineer", None, "medium")
        assert isinstance(qs, list)
        assert len(qs) == 3

    def test_generate_questions_company_specific(self):
        from app.agents.interview_coach_agent import generate_questions
        qs = generate_questions("company_specific", 3, "SWE", "amazon", "hard")
        assert len(qs) == 3

    def test_question_bank_company_profiles(self):
        from app.agents.interview_question_bank import COMPANY_PROFILES, get_company_profile
        assert len(COMPANY_PROFILES) >= 8
        assert get_company_profile("google") is not None
        assert get_company_profile("amazon") is not None
        assert get_company_profile("tcs")    is not None
        assert get_company_profile("unknown_company_xyz") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Report Generation
# ═══════════════════════════════════════════════════════════════════════════════
class TestReportGeneration:
    def _sample_questions(self) -> list[dict]:
        return [
            {"question": "Tell me about yourself.", "type": "hr",
             "score": 72.0, "answer_snippet": "I am a software engineer..."},
            {"question": "Explain hash tables.", "type": "technical",
             "score": 68.0, "answer_snippet": "A hash table maps keys..."},
            {"question": "Describe a challenge you overcame.", "type": "behavioural",
             "score": 80.0, "answer_snippet": "During my project..."},
        ]

    def test_report_returns_session_report(self):
        from app.agents.interview_coach_agent import generate_session_report
        qs  = self._sample_questions()
        avg = {"overall": 73.3, "technical": 68.0, "confidence": 70.0,
               "communication": 72.0, "relevance": 75.0, "completeness": 65.0}
        r   = generate_session_report("hr", "ML Engineer", None, qs, avg)
        assert 0 <= r.overall_score <= 100
        assert r.grade in ("A", "B", "C", "D", "F")

    def test_grade_a_for_high_score(self):
        from app.agents.interview_coach_agent import _score_to_grade
        assert _score_to_grade(88) == "A"
        assert _score_to_grade(72) == "B"
        assert _score_to_grade(56) == "C"
        assert _score_to_grade(42) == "D"
        assert _score_to_grade(25) == "F"

    def test_evaluate_with_ai_returns_feedback(self):
        from app.agents.interview_coach_agent import evaluate_answer_with_ai
        fb = evaluate_answer_with_ai(
            "Tell me about a project.",
            GOOD_BEHAVIOURAL,
            "behavioural",
            "ML Engineer",
        )
        assert fb.scores.overall_score > 0
        assert isinstance(fb.model_answer, str)
        assert len(fb.model_answer) > 20


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestInterviewAPI:
    @pytest.fixture(scope="class")
    def headers(self, client):
        return get_auth_headers(client, "api")

    # ── Company list ──────────────────────────────────────────────────────────
    def test_list_companies(self, client, headers):
        r = client.get("/api/v1/interview/companies", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 8
        keys = [c["key"] for c in data["companies"]]
        assert "google"  in keys
        assert "amazon"  in keys
        assert "tcs"     in keys

    def test_list_companies_no_auth(self, client):
        r = client.get("/api/v1/interview/companies")
        assert r.status_code == 403

    # ── Start session ─────────────────────────────────────────────────────────
    def test_start_hr_session(self, client, headers):
        r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "medium",
            "target_role": "ML Engineer", "total_questions": 3,
        }, headers=headers)
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["session_id"] > 0
        assert data["total_questions"] == 3
        assert data["current_question"] is not None
        assert data["current_question"]["question_number"] == 1

    def test_start_technical_session(self, client, headers):
        r = client.post("/api/v1/interview/sessions", json={
            "mode": "technical", "difficulty": "hard",
            "target_role": "Backend Engineer", "total_questions": 2,
        }, headers=headers)
        assert r.status_code == 201

    def test_start_company_specific(self, client, headers):
        r = client.post("/api/v1/interview/sessions", json={
            "mode":           "company_specific",
            "difficulty":     "medium",
            "target_role":    "SWE",
            "target_company": "google",
            "total_questions": 2,
        }, headers=headers)
        assert r.status_code == 201

    def test_start_session_invalid_mode(self, client, headers):
        r = client.post("/api/v1/interview/sessions", json={
            "mode": "dancing", "difficulty": "medium", "total_questions": 3,
        }, headers=headers)
        assert r.status_code in (400, 422)

    def test_start_session_too_many_questions(self, client, headers):
        r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy", "total_questions": 20,
        }, headers=headers)
        assert r.status_code == 422

    # ── Full lifecycle ────────────────────────────────────────────────────────
    def test_full_session_lifecycle(self, client, headers):
        """Start → get current question → submit answers → complete → get report."""
        # 1. Start
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy",
            "target_role": "Junior Developer", "total_questions": 2,
        }, headers=headers)
        assert start_r.status_code == 201
        session_id = start_r.json()["data"]["session_id"]

        # 2. Get current question
        q_r = client.get(
            f"/api/v1/interview/sessions/{session_id}/current-question",
            headers=headers
        )
        assert q_r.status_code == 200
        q_data = q_r.json()["data"]
        assert q_data["session_complete"] is False
        assert q_data["current_question"]["question_number"] == 1

        # 3. Submit answer for Q1
        ans1 = client.post(
            f"/api/v1/interview/sessions/{session_id}/answer",
            json={"question_number": 1, "answer_text": GOOD_BEHAVIOURAL,
                  "time_taken_seconds": 120},
            headers=headers,
        )
        assert ans1.status_code == 200
        eval_data = ans1.json()["data"]
        assert "evaluation" in eval_data
        assert "scores"     in eval_data["evaluation"]
        assert eval_data["evaluation"]["scores"]["overall"] > 0
        assert "model_answer" in eval_data

        # 4. Submit answer for Q2
        ans2 = client.post(
            f"/api/v1/interview/sessions/{session_id}/answer",
            json={"question_number": 2, "answer_text": GOOD_BEHAVIOURAL,
                  "time_taken_seconds": 90},
            headers=headers,
        )
        assert ans2.status_code == 200
        assert ans2.json()["data"]["session_complete"] is True

        # 5. Complete session
        complete_r = client.post(
            f"/api/v1/interview/sessions/{session_id}/complete",
            headers=headers,
        )
        assert complete_r.status_code == 200
        report = complete_r.json()["data"]
        assert "scores"            in report
        assert "grade"             in report["scores"]
        assert report["scores"]["grade"] in ("A", "B", "C", "D", "F")
        assert "executive_summary" in report
        assert "improvement_tips"  in report
        assert report["questions_answered"] == 2

        # 6. Get report via dedicated endpoint
        rep_r = client.get(
            f"/api/v1/interview/sessions/{session_id}/report",
            headers=headers,
        )
        assert rep_r.status_code == 200
        assert rep_r.json()["data"]["report_id"] == report["report_id"]

    def test_double_answer_rejected(self, client, headers):
        """Submitting an answer twice for the same question returns 422."""
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy", "total_questions": 2,
        }, headers=headers)
        sid = start_r.json()["data"]["session_id"]

        client.post(f"/api/v1/interview/sessions/{sid}/answer",
                    json={"question_number": 1, "answer_text": GOOD_BEHAVIOURAL},
                    headers=headers)
        r = client.post(f"/api/v1/interview/sessions/{sid}/answer",
                        json={"question_number": 1, "answer_text": "Another answer"},
                        headers=headers)
        assert r.status_code == 422

    def test_complete_with_no_answers_rejected(self, client, headers):
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "technical", "difficulty": "medium", "total_questions": 3,
        }, headers=headers)
        sid = start_r.json()["data"]["session_id"]
        r   = client.post(f"/api/v1/interview/sessions/{sid}/complete",
                          headers=headers)
        assert r.status_code == 422

    def test_abandon_session(self, client, headers):
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy", "total_questions": 2,
        }, headers=headers)
        sid = start_r.json()["data"]["session_id"]
        r   = client.post(f"/api/v1/interview/sessions/{sid}/abandon",
                          headers=headers)
        assert r.status_code == 200

        # Session detail should reflect abandoned status
        detail_r = client.get(f"/api/v1/interview/sessions/{sid}",
                               headers=headers)
        assert detail_r.json()["data"]["status"] == "abandoned"

    def test_list_sessions(self, client, headers):
        r = client.get("/api/v1/interview/sessions", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 1
        assert isinstance(data["sessions"], list)

    def test_session_not_accessible_by_other_user(self, client, headers):
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy", "total_questions": 2,
        }, headers=headers)
        sid    = start_r.json()["data"]["session_id"]
        other  = get_auth_headers(client, "other_iv")
        r      = client.get(f"/api/v1/interview/sessions/{sid}", headers=other)
        assert r.status_code == 404

    def test_get_nonexistent_session(self, client, headers):
        r = client.get("/api/v1/interview/sessions/99999", headers=headers)
        assert r.status_code == 404

    def test_submit_empty_answer_rejected(self, client, headers):
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy", "total_questions": 2,
        }, headers=headers)
        sid = start_r.json()["data"]["session_id"]
        r   = client.post(f"/api/v1/interview/sessions/{sid}/answer",
                          json={"question_number": 1, "answer_text": "Hi"},
                          headers=headers)
        assert r.status_code == 422

    def test_get_report_before_complete_returns_404(self, client, headers):
        start_r = client.post("/api/v1/interview/sessions", json={
            "mode": "hr", "difficulty": "easy", "total_questions": 2,
        }, headers=headers)
        sid = start_r.json()["data"]["session_id"]
        r   = client.get(f"/api/v1/interview/sessions/{sid}/report",
                         headers=headers)
        assert r.status_code == 404
