"""
tests/test_notifications.py
──────────────────────────────
Integration tests for the notification system: creation, listing,
unread-count badge, mark-as-read, mark-all-read, and delete.

Uses TestClient with an in-memory SQLite DB and mocked Redis, matching the
conventions in tests/test_auth.py.

NOT EXECUTED IN SANDBOX: this file requires fastapi, sqlalchemy, and every
other backend dependency, none of which are installed in the sandbox this
was written in (no network access to pip install). It is believed correct
based on tracing the actual endpoint/service code
(app/api/v1/endpoints/notifications.py, app/services/notification_service.py)
line-by-line against these assertions, but has not been run through pytest.
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

TEST_DATABASE_URL = "sqlite:///./test_notifications.db"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


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
    mock = MagicMock()
    mock.exists.return_value = 0
    yield mock


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db]    = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client() -> TestClient:
    with patch("app.db.session.check_database_connection", return_value=True), \
         patch("app.db.redis.check_redis_connection", return_value=True):
        with TestClient(app) as c:
            yield c


VALID_USER = {
    "full_name": "Notif Test User",
    "email":     "notiftest@example.com",
    "password":  "Str0ng!Pass",
}


def register_and_login(client: TestClient) -> dict:
    client.post("/api/v1/auth/register", json=VALID_USER)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    return resp.json()["data"]["tokens"]


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _create_notification_directly(user_id: int) -> int:
    """
    Bypasses the API (no endpoint exists purely for creating a test
    notification as a user — they're created server-side by the AI
    services) and calls the service layer directly against the test DB,
    the same way resume/skill-gap/career/interview services do via
    app.services.notification_service.notify().
    """
    from app.models.notification import NotificationType
    from app.services.notification_service import notify

    db = TestSession()
    try:
        entry = notify(
            db, user_id=user_id, type=NotificationType.RESUME_ANALYSIS_COMPLETED,
            title="Resume analysis complete", message="Your resume scored 82/100.",
            action_url="/resume/1/report",
        )
        db.commit()
        return entry.notification_id
    finally:
        db.close()


class TestNotificationCreation:
    def test_notify_persists_to_db(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]
        notif_id = _create_notification_directly(me["user_id"])
        assert notif_id is not None

        r = client.get("/api/v1/notifications", headers=auth_headers(tokens))
        assert r.status_code == 200
        body = r.json()["data"]
        assert body["total"] >= 1
        assert any(n["notification_id"] == notif_id for n in body["notifications"])


class TestNotificationListing:
    def test_list_requires_auth(self, client: TestClient) -> None:
        r = client.get("/api/v1/notifications")
        assert r.status_code == 401

    def test_list_pagination_fields_present(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "listpage@example.com")
        r = client.get("/api/v1/notifications?page=1&page_size=5", headers=auth_headers(tokens))
        assert r.status_code == 200
        data = r.json()["data"]
        for field in ("total", "unread_count", "page", "page_size", "total_pages", "notifications"):
            assert field in data

    def test_search_filters_by_title_or_message(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "search@example.com")
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]
        _create_notification_directly(me["user_id"])
        r = client.get("/api/v1/notifications?search=resume", headers=auth_headers(tokens))
        assert r.status_code == 200
        assert r.json()["data"]["total"] >= 1
        r2 = client.get("/api/v1/notifications?search=zzz_no_match_zzz", headers=auth_headers(tokens))
        assert r2.json()["data"]["total"] == 0


class TestUnreadCountBadge:
    def test_unread_count_increases_on_create(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "badge@example.com")
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]

        before = client.get("/api/v1/notifications/unread-count", headers=auth_headers(tokens))
        before_count = before.json()["data"]["unread_count"]

        _create_notification_directly(me["user_id"])

        after = client.get("/api/v1/notifications/unread-count", headers=auth_headers(tokens))
        after_count = after.json()["data"]["unread_count"]
        assert after_count == before_count + 1

    def test_unread_count_decreases_after_mark_read(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "badgeread@example.com")
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]
        notif_id = _create_notification_directly(me["user_id"])

        before = client.get("/api/v1/notifications/unread-count", headers=auth_headers(tokens)).json()["data"]["unread_count"]
        client.patch(f"/api/v1/notifications/{notif_id}/read", headers=auth_headers(tokens))
        after = client.get("/api/v1/notifications/unread-count", headers=auth_headers(tokens)).json()["data"]["unread_count"]
        assert after == before - 1


class TestMarkReadUnread:
    def test_mark_one_read(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "markone@example.com")
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]
        notif_id = _create_notification_directly(me["user_id"])

        r = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=auth_headers(tokens))
        assert r.status_code == 200
        assert r.json()["data"]["is_read"] is True

    def test_mark_read_nonexistent_returns_404(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "marknone@example.com")
        r = client.patch("/api/v1/notifications/999999/read", headers=auth_headers(tokens))
        assert r.status_code == 404

    def test_mark_all_read(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "markall@example.com")
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]
        _create_notification_directly(me["user_id"])
        _create_notification_directly(me["user_id"])

        r = client.post("/api/v1/notifications/mark-all-read", headers=auth_headers(tokens))
        assert r.status_code == 200
        assert r.json()["data"]["marked_read"] >= 2

        unread = client.get("/api/v1/notifications/unread-count", headers=auth_headers(tokens))
        assert unread.json()["data"]["unread_count"] == 0

    def test_users_cannot_mark_read_other_users_notifications(self, client: TestClient) -> None:
        """A user must never be able to mark another user's notification as
        read via a guessed ID — the service scopes every query by user_id."""
        tokens_a = register_and_login_unique(client, "usera@example.com")
        me_a = client.get("/api/v1/users/me", headers=auth_headers(tokens_a)).json()["data"]
        notif_id = _create_notification_directly(me_a["user_id"])

        tokens_b = register_and_login_unique(client, "userb@example.com")
        r = client.patch(f"/api/v1/notifications/{notif_id}/read", headers=auth_headers(tokens_b))
        assert r.status_code == 404  # not "not yours" — scoped query returns not-found


class TestNotificationDelete:
    def test_delete_notification(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "delete@example.com")
        me = client.get("/api/v1/users/me", headers=auth_headers(tokens)).json()["data"]
        notif_id = _create_notification_directly(me["user_id"])

        r = client.delete(f"/api/v1/notifications/{notif_id}", headers=auth_headers(tokens))
        assert r.status_code == 200

        listed = client.get("/api/v1/notifications", headers=auth_headers(tokens)).json()["data"]
        assert not any(n["notification_id"] == notif_id for n in listed["notifications"])

    def test_delete_nonexistent_returns_404(self, client: TestClient) -> None:
        tokens = register_and_login_unique(client, "deletenone@example.com")
        r = client.delete("/api/v1/notifications/999999", headers=auth_headers(tokens))
        assert r.status_code == 404


# ── Helper: register a fresh user per test to avoid state bleed between tests ──
def register_and_login_unique(client: TestClient, email: str) -> dict:
    client.post("/api/v1/auth/register", json={**VALID_USER, "email": email})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": VALID_USER["password"]})
    return resp.json()["data"]["tokens"]
