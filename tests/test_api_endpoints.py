"""
tests/test_api_endpoints.py
Integration tests for FastAPI REST API endpoints and RBAC security guards.
Strictly offline: uses TestClient and isolated SQLite database. 0 external network calls.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.account.service import AccountService
from app.api.main import create_app
from app.models.schema import Base, Script, Style, User
import app.core.database as core_db


@pytest.fixture
def test_client(tmp_path, monkeypatch):
    """Provide a TestClient connected to an isolated test database."""
    db_file = tmp_path / "test_api.db"
    test_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    monkeypatch.setattr(core_db, "engine", test_engine)
    monkeypatch.setattr(core_db, "SessionLocal", TestingSession)

    # Seed default accounts in test DB
    account_service = AccountService()
    account_service.ensure_default_accounts()

    # Seed a test script
    with TestingSession() as session:
        style = Style(style_id="default_style", name="Default Creator", version=1)
        session.add(style)
        script = Script(
            script_id="scr_test001",
            user_id="usr_creator",
            style_id="default_style",
            premise="Test premise for comedy",
            script_text="INT. CAFE - DAY\nPRIYA\nHello!\nBLACKOUT.",
            status="draft",
        )
        session.add(script)
        session.commit()

    fastapi_app = create_app()
    client = TestClient(fastapi_app)
    return client


def test_health_check(test_client):
    res = test_client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_auth_login_success_and_failure(test_client):
    # Invalid credentials
    res_fail = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": "wrongpassword"},
    )
    assert res_fail.status_code == 401

    # Valid admin login
    res_admin = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": "admin123"},
    )
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert data["role"] == "admin"
    assert "access_token" in data

    # Valid creator user login
    res_creator = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "creator", "password": "creator123"},
    )
    assert res_creator.status_code == 200
    assert res_creator.json()["role"] == "user"


def test_auth_me(test_client):
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": "admin123"},
    )
    token = login_res.json()["access_token"]

    res = test_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["username"] == "admin"
    assert res.json()["role"] == "admin"


def test_rbac_guard_blocks_regular_user(test_client):
    """Verify regular user cannot access admin benchmarks (403 Forbidden)."""
    # 1. Log in as regular user
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "creator", "password": "creator123"},
    )
    user_token = login_res.json()["access_token"]

    # 2. Try to access admin benchmarks
    res = test_client.get(
        "/api/v1/admin/benchmarks",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert res.status_code == 403
    assert "administrator permissions required" in res.json()["detail"].lower()


def test_rbac_guard_permits_admin(test_client):
    """Verify admin can access admin benchmarks (200 OK)."""
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": "admin123"},
    )
    admin_token = login_res.json()["access_token"]

    res = test_client.get(
        "/api/v1/admin/benchmarks",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "total_videos" in data
    assert "total_scripts" in data


def test_user_script_list_and_detail(test_client):
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "creator", "password": "creator123"},
    )
    token = login_res.json()["access_token"]

    # List scripts
    res = test_client.get(
        "/api/v1/scripts",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    scripts = res.json()
    assert len(scripts) >= 1
    assert scripts[0]["script_id"] == "scr_test001"

    # Detail script
    res_detail = test_client.get(
        "/api/v1/scripts/scr_test001",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_detail.status_code == 200
    payload = res_detail.json()
    assert payload["script_id"] == "scr_test001"
    assert len(payload["parsed_elements"]) > 0


def test_admin_update_script_review(test_client):
    login_res = test_client.post(
        "/api/v1/auth/login",
        json={"username_or_email": "admin", "password": "admin123"},
    )
    admin_token = login_res.json()["access_token"]

    review_payload = {
        "status": "approved",
        "rating": 5,
        "review_notes": "Flawless comedic timing and punchline.",
    }
    res = test_client.post(
        "/api/v1/admin/scripts/scr_test001/review",
        json=review_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 200
    updated = res.json()
    assert updated["status"] == "approved"
    assert updated["rating"] == 5
    assert "Flawless" in updated["review_notes"]
