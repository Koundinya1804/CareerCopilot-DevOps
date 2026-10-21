"""
tests/test_auth.py
──────────────────
Integration tests for authentication and user endpoints.
Uses TestClient with an in-memory SQLite DB and mocked Redis.
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

# ── Test DB (SQLite in-memory) ─────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
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
    mock.pipeline.return_value.__enter__ = lambda s: s
    mock.pipeline.return_value.__exit__  = MagicMock(return_value=False)
    mock.pipeline.return_value.execute.return_value = [1, True]
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


# ── Helpers ───────────────────────────────────────────────────────────────────
VALID_USER = {
    "full_name": "Test User",
    "email":     "test@example.com",
    "password":  "Str0ng!Pass",
}


def register_and_login(client: TestClient, user: dict = VALID_USER) -> dict:
    client.post("/api/v1/auth/register", json=user)
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    return resp.json()["data"]["tokens"]


# ── Health ────────────────────────────────────────────────────────────────────
class TestHealth:
    def test_liveness(self, client: TestClient) -> None:
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ── Registration ──────────────────────────────────────────────────────────────
class TestRegister:
    def test_register_success(self, client: TestClient) -> None:
        r = client.post("/api/v1/auth/register", json=VALID_USER)
        assert r.status_code == 201
        body = r.json()
        assert body["success"] is True
        assert body["data"]["email"] == VALID_USER["email"]
        assert body["data"]["role"]  == "user"

    def test_register_duplicate_email(self, client: TestClient) -> None:
        r = client.post("/api/v1/auth/register", json=VALID_USER)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "RESOURCE_CONFLICT"

    def test_register_weak_password(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/auth/register",
            json={**VALID_USER, "email": "weak@example.com", "password": "weakpass"},
        )
        assert r.status_code == 422

    def test_register_invalid_email(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/auth/register",
            json={**VALID_USER, "email": "not-an-email"},
        )
        assert r.status_code == 422

    def test_register_short_name(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/auth/register",
            json={**VALID_USER, "email": "short@example.com", "full_name": "X"},
        )
        assert r.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────
class TestLogin:
    def test_login_success(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
        )
        assert r.status_code == 200
        tokens = r.json()["data"]["tokens"]
        assert "access_token"  in tokens
        assert "refresh_token" in tokens
        assert tokens["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": VALID_USER["email"], "password": "WrongPass1"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_login_unknown_email(self, client: TestClient) -> None:
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Str0ng!Pass"},
        )
        assert r.status_code == 401


# ── Protected Routes ──────────────────────────────────────────────────────────
class TestProtectedRoutes:
    def test_me_without_token(self, client: TestClient) -> None:
        r = client.get("/api/v1/users/me")
        assert r.status_code == 403  # HTTPBearer raises 403 when header missing

    def test_me_with_invalid_token(self, client: TestClient) -> None:
        r = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer this.is.garbage"},
        )
        assert r.status_code == 401

    def test_me_authenticated(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        r = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["email"] == VALID_USER["email"]

    def test_admin_endpoint_forbidden_for_user(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        r = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert r.status_code == 403


# ── Token Refresh ─────────────────────────────────────────────────────────────
class TestTokenRefresh:
    def test_refresh_success(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert r.status_code == 200
        new_tokens = r.json()["data"]
        assert "access_token" in new_tokens
        assert new_tokens["access_token"] != tokens["access_token"]

    def test_refresh_with_access_token_fails(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["access_token"]},  # wrong type
        )
        assert r.status_code == 401


# ── Profile ───────────────────────────────────────────────────────────────────
class TestProfile:
    def test_upsert_profile(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        r = client.put(
            "/api/v1/users/me/profile",
            json={
                "target_role":      "Senior ML Engineer",
                "years_experience": 3,
                "location":         "Hyderabad, IN",
            },
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["target_role"] == "Senior ML Engineer"

    def test_add_skill(self, client: TestClient) -> None:
        tokens = register_and_login(client)
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        r = client.post(
            "/api/v1/users/me/skills",
            json={"skill_name": "Python", "proficiency": "expert", "years_used": 3},
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["data"]["skill_name"] == "Python"
