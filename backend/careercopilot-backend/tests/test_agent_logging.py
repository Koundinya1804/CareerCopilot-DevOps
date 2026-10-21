"""
tests/test_agent_logging.py
──────────────────────────────
Tests for app/services/agent_log_service.py — the log_call()/timed_agent_call()
write path used by every AI service, and the AgentAnalyticsService read path
consumed by the admin usage dashboard.

This exists because of a real bug found earlier in this project: none of the
AI services were actually calling log_call()/timed_agent_call() at all, so
the agent_logs table — and the entire analytics dashboard built on top of it
— was silently empty regardless of real usage. These tests assert the write
path actually persists rows and the read path actually aggregates them
correctly, so that class of "looks wired up but isn't" bug can't recur
unnoticed.

NOT EXECUTED IN SANDBOX — see tests/test_notifications.py docstring for why.
Verified by tracing app/services/agent_log_service.py and
app/models/agent_log.py line-by-line against these assertions.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base

TEST_DATABASE_URL = "sqlite:///./test_agent_logging.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def test_user(db):
    from app.models.user import User
    from app.core.security import hash_password
    user = User(
        full_name="Agent Log Test User", email="agentlogtest@example.com",
        password_hash=hash_password("Str0ng!Pass"),
        # status defaults to UserStatus.ACTIVE — is_active is a derived
        # @property (status == ACTIVE), not a settable column.
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestLogCallWritePath:
    def test_log_call_persists_a_row(self, db, test_user):
        from app.models.agent_log import AgentLogStatus, AgentName
        from app.services.agent_log_service import log_call

        entry = log_call(
            db, user_id=test_user.user_id, agent_name=AgentName.RESUME_ANALYSER,
            status=AgentLogStatus.SUCCESS, latency_ms=1200,
            input_tokens=500, output_tokens=300,
        )
        db.commit()
        assert entry.log_id is not None
        assert entry.user_id == test_user.user_id
        assert entry.agent_name == AgentName.RESUME_ANALYSER
        assert entry.status == AgentLogStatus.SUCCESS

    def test_log_call_computes_estimated_cost(self, db, test_user):
        from app.models.agent_log import AgentLogStatus, AgentName
        from app.services.agent_log_service import log_call

        entry = log_call(
            db, user_id=test_user.user_id, agent_name=AgentName.SKILL_GAP,
            status=AgentLogStatus.SUCCESS, latency_ms=800,
            input_tokens=1_000_000, output_tokens=1_000_000,
        )
        db.commit()
        # Cost must reflect the actually-configured provider's pricing
        # (Groq llama-3.3-70b-versatile: $0.59 in / $0.79 out per 1M tokens
        # by default) — NOT a hardcoded Gemini price. This is a regression
        # guard for a real bug found in this project: cost estimates were
        # hardcoded to Gemini 2.0 Flash pricing ($0.075/$0.30) even though
        # the app runs on Groq by default.
        assert entry.estimated_cost_usd is not None
        assert entry.estimated_cost_usd > 0
        # With 1M+1M tokens the Gemini-priced estimate would be ~$0.375;
        # the Groq-priced estimate is ~$1.38 — assert we're in the Groq
        # ballpark, not the stale Gemini ballpark.
        assert entry.estimated_cost_usd > 1.0, (
            "Cost looks like it's using stale Gemini pricing instead of "
            "the actually-configured provider's pricing."
        )

    def test_log_call_handles_missing_token_counts_gracefully(self, db, test_user):
        from app.models.agent_log import AgentLogStatus, AgentName
        from app.services.agent_log_service import log_call

        entry = log_call(
            db, user_id=test_user.user_id, agent_name=AgentName.RAG_CHAIN,
            status=AgentLogStatus.SUCCESS, latency_ms=400,
        )
        db.commit()
        assert entry.estimated_cost_usd is None or entry.estimated_cost_usd == 0.0

    def test_timed_agent_call_records_latency_automatically(self, db, test_user):
        import time
        from app.models.agent_log import AgentName
        from app.services.agent_log_service import timed_agent_call

        with timed_agent_call(db, user_id=test_user.user_id, agent_name=AgentName.CAREER_RECOMMENDATION) as ctx:
            time.sleep(0.05)
            ctx["output_tokens"] = 42
        db.commit()

        from app.models.agent_log import AgentLog
        row = db.query(AgentLog).filter_by(user_id=test_user.user_id, agent_name=AgentName.CAREER_RECOMMENDATION).first()
        assert row is not None
        assert row.latency_ms >= 50
        assert row.output_tokens == 42

    def test_timed_agent_call_marks_failed_on_exception(self, db, test_user):
        from app.models.agent_log import AgentLog, AgentLogStatus, AgentName
        from app.services.agent_log_service import timed_agent_call

        with pytest.raises(ValueError):
            with timed_agent_call(db, user_id=test_user.user_id, agent_name=AgentName.INTERVIEW_COACH):
                raise ValueError("simulated agent failure")
        db.commit()

        row = (
            db.query(AgentLog)
            .filter_by(user_id=test_user.user_id, agent_name=AgentName.INTERVIEW_COACH)
            .order_by(AgentLog.log_id.desc())
            .first()
        )
        assert row is not None
        assert row.status == AgentLogStatus.FAILED


class TestAgentAnalyticsReadPath:
    def test_summary_totals_match_logged_calls(self, db, test_user):
        from app.models.agent_log import AgentLogStatus, AgentName
        from app.services.agent_log_service import AgentAnalyticsService, log_call

        log_call(db, user_id=test_user.user_id, agent_name=AgentName.RESUME_ANALYSER,
                  status=AgentLogStatus.SUCCESS, latency_ms=100, input_tokens=10, output_tokens=10)
        log_call(db, user_id=test_user.user_id, agent_name=AgentName.RESUME_ANALYSER,
                  status=AgentLogStatus.FAILED, latency_ms=50)
        db.commit()

        summary = AgentAnalyticsService(db).get_summary()
        assert summary["total_calls"] >= 2
        assert summary["successful_calls"] >= 1
        assert summary["failed_calls"] >= 1
        assert "total_input_tokens" in summary
        assert "total_output_tokens" in summary
        assert "avg_input_tokens" in summary

    def test_by_agent_breakdown_groups_correctly(self, db, test_user):
        from app.models.agent_log import AgentLogStatus, AgentName
        from app.services.agent_log_service import AgentAnalyticsService, log_call

        log_call(db, user_id=test_user.user_id, agent_name=AgentName.SKILL_GAP,
                  status=AgentLogStatus.SUCCESS, latency_ms=200)
        db.commit()

        by_agent = AgentAnalyticsService(db).get_by_agent()
        agent_names = [row["agent_name"] for row in by_agent["by_agent"]]
        assert AgentName.SKILL_GAP.value in agent_names

    def test_top_users_includes_active_user(self, db, test_user):
        from app.models.agent_log import AgentLogStatus, AgentName
        from app.services.agent_log_service import AgentAnalyticsService, log_call

        log_call(db, user_id=test_user.user_id, agent_name=AgentName.CAREER_RECOMMENDATION,
                  status=AgentLogStatus.SUCCESS, latency_ms=150)
        db.commit()

        top_users = AgentAnalyticsService(db).get_top_users(limit=10)
        user_ids = [row["user_id"] for row in top_users["top_users"]]
        assert test_user.user_id in user_ids
