"""API surface: health, auth, and that protected routes reject unauthenticated calls."""
from fastapi.testclient import TestClient

import main
from conftest import TEST_USERNAME, TEST_PASSWORD

client = TestClient(main.app)


def test_health_is_public():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_login_rejects_bad_credentials():
    r = client.post("/auth/login", json={"username": TEST_USERNAME, "password": "wrong"})
    assert r.status_code == 401


def test_login_rejects_unknown_user():
    r = client.post("/auth/login", json={"username": "nobody", "password": TEST_PASSWORD})
    assert r.status_code == 401


def test_login_succeeds_and_returns_token():
    r = client.post("/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    assert r.status_code == 200
    assert isinstance(r.json().get("token"), str) and r.json()["token"]


def test_analyse_requires_auth():
    # No Authorization header -> 401 before any analysis runs (no network hit).
    r = client.post("/api/analyse", json={"waypoints": [[-33.0, 151.0], [-33.1, 151.1]]})
    assert r.status_code == 401


def test_analyse_rejects_invalid_token():
    r = client.post(
        "/api/analyse",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"waypoints": [[-33.0, 151.0], [-33.1, 151.1]]},
    )
    assert r.status_code == 401
