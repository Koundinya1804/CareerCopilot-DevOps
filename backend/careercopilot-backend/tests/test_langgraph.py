"""
tests/test_langgraph.py
─────────────────────────
Tests for the LangGraph Multi-Agent System:

  Unit:
    - State schema validation
    - Supervisor routing (rule-based + edge cases)
    - Each agent node (mocked dependencies)
    - Memory store operations

  Integration:
    - Full graph invocation (mocked agents)
    - API endpoints (chat, classify, session CRUD)
    - Multi-turn conversation continuity
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.db.redis import get_redis
from app.main import app

# ── Test DB ───────────────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test_lg.db"
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
    m.get.return_value = None
    m.setex.return_value = True
    m.delete.return_value = True
    m.ttl.return_value = 86400
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
    Path("test_lg.db").unlink(missing_ok=True)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection",      return_value=True):
        with TestClient(app) as c:
            yield c


def get_auth_headers(client, suffix="lg"):
    client.post("/api/v1/auth/register", json={
        "full_name": f"LG User {suffix}", "email": f"lg_{suffix}@test.com",
        "password": "Str0ng!Pass",
    })
    r = client.post("/api/v1/auth/login", json={
        "email": f"lg_{suffix}@test.com", "password": "Str0ng!Pass",
    })
    return {"Authorization": f"Bearer {r.json()['data']['tokens']['access_token']}"}


SAMPLE_RESUME = """
Priya Sharma — ML Engineer
priya@example.com | github.com/priya | linkedin.com/in/priya

SKILLS: Python, PyTorch, scikit-learn, NumPy, Pandas, FastAPI, Docker, Git, SQL

EXPERIENCE:
ML Engineer — Swiggy (Jan 2022 - Present)
- Built recommendation engine; improved CTR by 25%
- Deployed models with Docker and Kubernetes

EDUCATION: B.Tech Computer Science — IIT Hyderabad 2019
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — State Schema
# ═══════════════════════════════════════════════════════════════════════════════
class TestStateSchema:
    def test_initial_state_created(self):
        from app.langgraph.state import initial_state
        s = initial_state(user_id=1, query="Hello", session_id="test-123")
        assert s["user_id"]        == 1
        assert s["original_query"] == "Hello"
        assert s["session_id"]     == "test-123"
        assert s["next_agent"]     == "supervisor"
        assert s["iteration"]      == 0
        assert s["has_error"]      is False

    def test_initial_state_messages(self):
        from app.langgraph.state import initial_state
        s = initial_state(user_id=1, query="Test query", session_id="s1")
        assert len(s["messages"]) == 1
        assert s["messages"][0]["role"]    == "user"
        assert s["messages"][0]["content"] == "Test query"

    def test_initial_state_defaults(self):
        from app.langgraph.state import initial_state
        s = initial_state(user_id=2, query="?", session_id="s2")
        assert s["user_skills"]    == []
        assert s["user_interests"] == []
        assert s["max_iterations"] == 5
        assert s["citations"]      == []

    def test_message_accumulator(self):
        from app.langgraph.state import _append
        result = _append([{"a": 1}], [{"b": 2}, {"c": 3}])
        assert len(result) == 3

    def test_message_accumulator_single(self):
        from app.langgraph.state import _append
        result = _append([], {"role": "user", "content": "hi"})
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Supervisor Routing
# ═══════════════════════════════════════════════════════════════════════════════
class TestSupervisorRouting:
    def test_resume_routing(self):
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("Can you analyse my resume?")
        assert result is not None
        assert result[0] == "resume_agent"
        assert result[2] >= 0.8

    def test_skill_gap_routing(self):
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("What skill gap do I have for ML Engineer?")
        assert result is not None
        assert result[0] == "skill_gap_agent"

    def test_career_routing(self):
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("What career should I pursue?")
        assert result is not None
        assert result[0] == "career_agent"

    def test_interview_routing(self):
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("Give me mock interview questions")
        assert result is not None
        assert result[0] == "interview_agent"

    def test_rag_routing_what_is(self):
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("What is the difference between TCP and UDP?")
        assert result is not None
        assert result[0] == "rag_agent"

    def test_salary_routing_career(self):
        # Regression test for the routing-audit fix: salary questions used to
        # be hardcoded to rag_agent (Knowledge Agent). Salary is a career
        # planning question, not a knowledge-base lookup — it now routes to
        # career_agent. See CHANGELOG.md "Supervisor Routing Audit".
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("What is the salary for an ML Engineer in India?")
        assert result is not None
        assert result[0] == "career_agent"

    def test_unknown_returns_none(self):
        from app.langgraph.nodes.supervisor import _rule_based_route
        result = _rule_based_route("xyzzy quux blergh")
        assert result is None

    def test_multi_step_detection(self):
        from app.langgraph.nodes.supervisor import _detect_multi_step
        assert _detect_multi_step("Analyse my resume and then give career advice") is True
        assert _detect_multi_step("What is Python?") is False

    def test_resume_required_detection(self):
        from app.langgraph.nodes.supervisor import _detect_resume_required
        assert _detect_resume_required("Analyse my resume") is True
        assert _detect_resume_required("What is SQL?")      is False

    def test_supervisor_node_increments_iteration(self):
        from app.langgraph.nodes.supervisor import supervisor_node
        from app.langgraph.state import initial_state
        s      = initial_state(user_id=1, query="What is Python?", session_id="s1")
        result = supervisor_node(s)
        assert result["iteration"] == 1

    def test_supervisor_node_sets_next_agent(self):
        from app.langgraph.nodes.supervisor import supervisor_node
        from app.langgraph.state import initial_state
        s      = initial_state(user_id=1, query="Analyse my resume", session_id="s2")
        result = supervisor_node(s)
        assert result["next_agent"] == "resume_agent"

    def test_supervisor_stops_at_max_iterations(self):
        from app.langgraph.nodes.supervisor import supervisor_node
        from app.langgraph.state import initial_state
        s            = initial_state(user_id=1, query="Query", session_id="s3")
        s["iteration"]      = 5
        s["max_iterations"] = 5
        result = supervisor_node(s)
        assert result["next_agent"] == "END"
        assert result["has_error"]  is True

    def test_route_after_supervisor_error(self):
        from app.langgraph.nodes.supervisor import route_after_supervisor
        from app.langgraph.state import initial_state
        s            = initial_state(user_id=1, query="Q", session_id="s4")
        s["has_error"]   = True
        s["next_agent"]  = "resume_agent"
        assert route_after_supervisor(s) == "END"

    def test_route_after_supervisor_normal(self):
        from app.langgraph.nodes.supervisor import route_after_supervisor
        from app.langgraph.state import initial_state
        s           = initial_state(user_id=1, query="Q", session_id="s5")
        s["next_agent"] = "rag_agent"
        assert route_after_supervisor(s) == "rag_agent"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Agent Nodes (mocked dependencies)
# ═══════════════════════════════════════════════════════════════════════════════
class TestAgentNodes:
    def _make_state(self, query="test", resume=SAMPLE_RESUME):
        from app.langgraph.state import initial_state
        s = initial_state(user_id=1, query=query, session_id=str(uuid.uuid4()),
                          resume_text=resume, user_skills=["Python", "PyTorch"])
        s["target_role"]    = "ML Engineer"
        s["years_experience"] = 3.0
        return s

    # Resume node
    def test_resume_node_no_text(self):
        from app.langgraph.nodes.agent_nodes import resume_node
        from app.langgraph.state import initial_state
        s      = initial_state(1, "analyse resume", "s1", resume_text=None)
        result = resume_node(s)
        assert "error" in (result.get("resume_output") or {})

    def test_resume_node_with_text(self):
        from app.langgraph.nodes.agent_nodes import resume_node
        s      = self._make_state()
        result = resume_node(s)
        if not result.get("has_error"):
            assert result.get("resume_output") is not None
            assert "ATS Score" in (result.get("final_response") or "")

    # Skill gap node
    def test_skill_gap_node_no_skills(self):
        from app.langgraph.nodes.agent_nodes import skill_gap_node
        from app.langgraph.state import initial_state
        s      = initial_state(1, "skill gap", "s1")
        result = skill_gap_node(s)
        assert "error" in (result.get("skill_gap_output") or {}) or result.get("has_error")

    def test_skill_gap_node_with_skills(self):
        from app.langgraph.nodes.agent_nodes import skill_gap_node
        s      = self._make_state("What skills am I missing for ML Engineer?")
        result = skill_gap_node(s)
        if not result.get("has_error"):
            assert result.get("skill_gap_output") is not None

    # Career node
    def test_career_node_no_data(self):
        from app.langgraph.nodes.agent_nodes import career_node
        from app.langgraph.state import initial_state
        s      = initial_state(1, "career advice", "s1")
        result = career_node(s)
        # Should handle gracefully
        assert result is not None

    def test_career_node_with_skills(self):
        from app.langgraph.nodes.agent_nodes import career_node
        s      = self._make_state("What career suits me?")
        result = career_node(s)
        if not result.get("has_error"):
            assert result.get("career_output") is not None

    # Interview node
    def test_interview_node_generates_questions(self):
        from app.langgraph.nodes.agent_nodes import interview_node
        s      = self._make_state("Give me interview questions for ML Engineer")
        result = interview_node(s)
        if not result.get("has_error"):
            out = result.get("interview_output") or {}
            assert out.get("type") == "questions"
            assert len(out.get("questions", [])) > 0

    # RAG node
    def test_rag_node_returns_answer(self):
        from app.langgraph.nodes.agent_nodes import rag_node
        from unittest.mock import patch
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="A deadlock occurs when two processes...",
            citations=[],
            chunks_used=3,
            categories=["operating_systems"],
            model_used="gemini-2.0-flash",
            latency_ms=800, tokens_used=200,
            query="What is deadlock?", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            s      = self._make_state("What is deadlock?")
            result = rag_node(s)
        assert result.get("rag_output") is not None
        assert "deadlock" in (result.get("final_response") or "").lower()

    # Error handler
    def test_error_handler_formats_response(self):
        from app.langgraph.nodes.agent_nodes import error_handler_node
        from app.langgraph.state import initial_state
        s              = initial_state(1, "Q", "s1")
        s["has_error"] = True
        s["error"]     = "Connection timeout"
        s["error_agent"] = "rag_agent"
        result         = error_handler_node(s)
        assert "error" in (result.get("final_response") or "").lower() or \
               "issue" in (result.get("final_response") or "").lower()

    # Response builder
    def test_response_builder_suggests_actions(self):
        from app.langgraph.nodes.agent_nodes import response_builder_node
        from app.langgraph.state import initial_state
        s                = initial_state(1, "Q", "s1")
        s["agent_chain"] = ["supervisor", "resume_agent"]
        s["final_response"] = "Your ATS score is 75."
        result           = response_builder_node(s)
        assert isinstance(result.get("suggested_actions"), list)

    # Role mapper
    def test_role_mapper(self):
        from app.langgraph.nodes.agent_nodes import _map_to_role_key
        assert _map_to_role_key("ML Engineer")       == "ml_engineer"
        assert _map_to_role_key("AI engineer")        == "ai_engineer"
        assert _map_to_role_key("fullstack developer") == "fullstack_engineer"
        assert _map_to_role_key("java developer")     == "java_developer"
        assert _map_to_role_key("cloud engineer")     == "cloud_engineer"


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Memory Store
# ═══════════════════════════════════════════════════════════════════════════════
class TestMemoryStore:
    def _make_memory(self):
        from app.langgraph.memory.memory_store import GraphMemory
        mock_redis = MagicMock()
        mock_redis.get.return_value  = None
        mock_redis.setex.return_value = True
        mock_redis.delete.return_value = True
        mock_redis.ttl.return_value  = 86400
        return GraphMemory(mock_redis), mock_redis

    def test_save_and_load_state(self):
        import json
        from app.langgraph.memory.memory_store import GraphMemory
        mock_redis = MagicMock()
        state      = {"user_id": 1, "intent": "resume_analysis", "agent_chain": ["supervisor", "resume_agent"]}
        raw        = json.dumps(state)
        mock_redis.get.return_value = raw
        mock_redis.setex.return_value = True

        mem = GraphMemory(mock_redis)
        mem.save_state("sess-1", state)
        mock_redis.setex.assert_called_once()

        loaded = mem.load_state("sess-1")
        assert loaded["user_id"] == 1
        assert loaded["intent"]  == "resume_analysis"

    def test_load_state_returns_none_when_missing(self):
        mem, _ = self._make_memory()
        result  = mem.load_state("nonexistent-session")
        assert result is None

    def test_load_messages_returns_empty_list(self):
        mem, _ = self._make_memory()
        msgs    = mem.load_messages("empty-session")
        assert msgs == []

    def test_session_exists_false(self):
        mem, mock_redis = self._make_memory()
        mock_redis.exists.return_value = 0
        assert mem.session_exists("no-session") is False

    def test_session_exists_true(self):
        from app.langgraph.memory.memory_store import GraphMemory
        mock_redis = MagicMock()
        mock_redis.exists.return_value = 1
        mem = GraphMemory(mock_redis)
        assert mem.session_exists("exists") is True

    def test_delete_session(self):
        mem, mock_redis = self._make_memory()
        mem.delete_session("sess-del")
        mock_redis.delete.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Unit Tests — Graph Runner
# ═══════════════════════════════════════════════════════════════════════════════
class TestGraphRunner:
    def test_graph_builds_without_error(self):
        from app.langgraph.graph import build_graph
        graph = build_graph()
        assert graph is not None

    def test_run_graph_rag_query(self):
        from app.langgraph.graph import run_graph
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="A hash table maps keys to values.",
            citations=[], chunks_used=2, categories=["data_structures"],
            model_used="gemini-2.0-flash", latency_ms=500, tokens_used=150,
            query="What is a hash table?", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            result = run_graph(user_id=1, query="What is a hash table?")
        assert result["session_id"]
        assert "rag_agent" in result["agent_chain"]
        assert result["has_error"] is False
        assert "hash table" in result["final_response"].lower()

    def test_run_graph_error_handled(self):
        from app.langgraph.graph import run_graph
        with patch("app.rag.chains.rag_chain.get_rag_chain",
                   side_effect=Exception("DB connection lost")):
            result = run_graph(user_id=1, query="What is SQL?")
        assert result["has_error"] is True
        assert result["final_response"]   # error message present

    def test_run_graph_returns_session_id(self):
        from app.langgraph.graph import run_graph
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="TCP is reliable...", citations=[], chunks_used=1,
            categories=["computer_networks"], model_used="gemini-2.0-flash",
            latency_ms=400, tokens_used=100, query="What is TCP?", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            r1 = run_graph(user_id=1, query="What is TCP?", session_id="fixed-id")
        assert r1["session_id"] == "fixed-id"

    def test_run_graph_resume_without_text(self):
        from app.langgraph.graph import run_graph
        result = run_graph(user_id=1, query="Analyse my resume")
        # Should not crash even without resume text
        assert result["session_id"]
        assert "resume_agent" in result["agent_chain"]


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — API Endpoints
# ═══════════════════════════════════════════════════════════════════════════════
class TestAgentChatAPI:
    @pytest.fixture(scope="class")
    def headers(self, client):
        return get_auth_headers(client, "api")

    # ── Routing info ──────────────────────────────────────────────────────────
    def test_routing_info(self, client, headers):
        r = client.get("/api/v1/agent/routing-info", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data["agents"]) == 5
        assert data["multi_turn"] is True

    def test_routing_info_no_auth(self, client):
        r = client.get("/api/v1/agent/routing-info")
        assert r.status_code == 403

    # ── Intent classification ─────────────────────────────────────────────────
    def test_classify_resume_intent(self, client, headers):
        r = client.post("/api/v1/agent/classify",
                        json={"query": "Please analyse my resume"},
                        headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["predicted_agent"] == "resume_agent"
        assert data["confidence"]      >= 0.8

    def test_classify_skill_gap_intent(self, client, headers):
        r = client.post("/api/v1/agent/classify",
                        json={"query": "What skills am I missing for ML Engineer?"},
                        headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["predicted_agent"] == "skill_gap_agent"

    def test_classify_interview_intent(self, client, headers):
        r = client.post("/api/v1/agent/classify",
                        json={"query": "Start a mock interview for me"},
                        headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["predicted_agent"] == "interview_agent"

    def test_classify_rag_intent(self, client, headers):
        r = client.post("/api/v1/agent/classify",
                        json={"query": "What is the difference between TCP and UDP?"},
                        headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["predicted_agent"] == "rag_agent"

    def test_classify_multi_step_detected(self, client, headers):
        r = client.post("/api/v1/agent/classify",
                        json={"query": "Analyse my resume and also give career recommendations"},
                        headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["is_multi_step"] is True

    # ── Chat endpoint ─────────────────────────────────────────────────────────
    def test_chat_rag_query(self, client, headers):
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="ACID stands for Atomicity, Consistency, Isolation, Durability.",
            citations=[{"number": 1, "filename": "dbms.json", "category": "dbms",
                        "category_label": "DBMS", "score": 0.9, "excerpt": "ACID..."}],
            chunks_used=3, categories=["dbms"], model_used="gemini-2.0-flash",
            latency_ms=700, tokens_used=200, query="What is ACID?", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            r = client.post("/api/v1/agent/chat", json={
                "query":            "What is ACID in databases?",
                "user_skills":      ["Python", "SQL"],
                "user_interests":   ["databases"],
            }, headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["session_id"]
        assert "rag_agent" in data["agent_chain"]
        assert "ACID" in data["response"]
        assert isinstance(data["citations"], list)
        assert isinstance(data["suggested_actions"], list)

    def test_chat_no_auth(self, client):
        r = client.post("/api/v1/agent/chat",
                        json={"query": "What is Python?"})
        assert r.status_code == 403

    def test_chat_short_query_rejected(self, client, headers):
        r = client.post("/api/v1/agent/chat", json={"query": "Hi"},
                        headers=headers)
        assert r.status_code == 422

    def test_chat_returns_session_id(self, client, headers):
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="Python is a high-level programming language.",
            citations=[], chunks_used=1, categories=["python"],
            model_used="gemini-2.0-flash", latency_ms=400, tokens_used=80,
            query="What is Python?", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            r = client.post("/api/v1/agent/chat",
                            json={"query": "What is Python programming language?"},
                            headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["session_id"]

    def test_chat_session_continuity(self, client, headers):
        """Two requests with same session_id should work."""
        sid = str(uuid.uuid4())
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="Answer 1", citations=[], chunks_used=1,
            categories=["python"], model_used="gemini-2.0-flash",
            latency_ms=300, tokens_used=50, query="Q1", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            r1 = client.post("/api/v1/agent/chat",
                             json={"query": "What is Python?", "session_id": sid},
                             headers=headers)
            r2 = client.post("/api/v1/agent/chat",
                             json={"query": "Tell me more about Python generators",
                                   "session_id": sid},
                             headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["data"]["session_id"] == sid
        assert r2.json()["data"]["session_id"] == sid

    # ── Session endpoints ─────────────────────────────────────────────────────
    def test_get_session_not_found(self, client, headers):
        r = client.get("/api/v1/agent/sessions/nonexistent-session-id",
                       headers=headers)
        assert r.status_code == 404

    def test_delete_session(self, client, headers):
        r = client.delete("/api/v1/agent/sessions/any-session-id",
                          headers=headers)
        assert r.status_code == 200

    def test_get_session_messages_empty(self, client, headers):
        r = client.get("/api/v1/agent/sessions/empty-session/messages",
                       headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0

    # ── Streaming ─────────────────────────────────────────────────────────────
    def test_stream_endpoint_returns_event_stream(self, client, headers):
        from app.rag.chains.rag_chain import RAGResponse
        mock_resp = RAGResponse(
            answer="TCP provides reliable ordered delivery.",
            citations=[], chunks_used=2, categories=["computer_networks"],
            model_used="gemini-2.0-flash", latency_ms=500, tokens_used=120,
            query="What is TCP?", has_answer=True,
        )
        with patch("app.rag.chains.rag_chain.get_rag_chain", return_value=mock_resp):
            r = client.post("/api/v1/agent/chat/stream",
                            json={"query": "What is TCP protocol?"},
                            headers=headers)
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
