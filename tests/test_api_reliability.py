"""Reliability behaviours: request-id header and input limits on the analyse endpoint."""
from fastapi.testclient import TestClient

import main
from conftest import TEST_USERNAME, TEST_PASSWORD

client = TestClient(main.app)


def _auth() -> dict:
    r = client.post("/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_response_has_request_id():
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")


def test_analyse_rejects_too_many_waypoints():
    wps = [[-33.0 + i * 0.0001, 151.0] for i in range(200)]
    r = client.post("/api/analyse", json={"waypoints": wps}, headers=_auth())
    assert r.status_code == 422


def test_analyse_rejects_too_long_route():
    r = client.post("/api/analyse", json={"waypoints": [[-33.0, 151.0], [33.0, 10.0]]}, headers=_auth())
    assert r.status_code == 422


def test_analyse_rejects_out_of_range_coord():
    r = client.post("/api/analyse", json={"waypoints": [[91.0, 0.0], [0.0, 0.0]]}, headers=_auth())
    assert r.status_code == 422
