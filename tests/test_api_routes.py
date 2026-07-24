"""Saved-routes CRUD API, with auth scoping."""
from fastapi.testclient import TestClient

import main
from conftest import TEST_USERNAME, TEST_PASSWORD

client = TestClient(main.app)


def _auth_header() -> dict:
    r = client.post("/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_routes_require_auth():
    assert client.get("/api/routes").status_code == 401
    assert client.post("/api/routes", json={"name": "x", "waypoints": [[0, 0], [1, 1]]}).status_code == 401


def test_routes_crud_lifecycle():
    h = _auth_header()
    payload = {
        "name": "Sydney → Newcastle",
        "waypoints": [[-33.87, 151.21], [-32.93, 151.78]],
        "params": {"max_grade_pct": 1.0},
    }

    # Create
    r = client.post("/api/routes", json=payload, headers=h)
    assert r.status_code == 200
    route_id = r.json()["id"]
    assert r.json()["name"] == payload["name"]

    # List includes it
    r = client.get("/api/routes", headers=h)
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()["routes"]]
    assert route_id in ids
    entry = next(x for x in r.json()["routes"] if x["id"] == route_id)
    assert entry["n_waypoints"] == 2

    # Fetch full record
    r = client.get(f"/api/routes/{route_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["waypoints"] == payload["waypoints"]
    assert r.json()["params"] == {"max_grade_pct": 1.0}

    # Delete
    assert client.delete(f"/api/routes/{route_id}", headers=h).status_code == 200
    assert client.get(f"/api/routes/{route_id}", headers=h).status_code == 404


def test_save_route_rejects_too_few_waypoints():
    h = _auth_header()
    r = client.post("/api/routes", json={"name": "bad", "waypoints": [[0, 0]]}, headers=h)
    assert r.status_code == 422


def test_get_route_rejects_malformed_id():
    h = _auth_header()
    # Not a 32-char hex id → 400 (guards against path traversal in the local backend).
    assert client.get("/api/routes/..%2f..%2fetc", headers=h).status_code in (400, 404)
    assert client.get("/api/routes/not-a-real-id", headers=h).status_code == 400
