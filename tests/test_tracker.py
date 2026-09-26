"""Tests for the local ticket tracker (tracker/server.py) — exercised over real HTTP."""
import json
import os
import pathlib
import sys
import threading
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tracker"))
os.environ["TRACKER_QUIET"] = "1"

import server as tracker  # noqa: E402


@pytest.fixture
def base_url(tmp_path):
    httpd = tracker.make_server("127.0.0.1", 0, tmp_path / "t.db")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"} if body is not None else {}
    hdrs.update(headers or {})
    req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_projects_have_independent_ticket_sequences(base_url):
    assert call(base_url, "POST", "/api/projects", {"key": "trk", "name": "TrackAlong"})[0] == 201
    assert call(base_url, "POST", "/api/projects", {"key": "WEB", "name": "Website"})[0] == 201

    s, t1 = call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "Crash on load", "type": "bug"})
    assert s == 201 and t1["ref"] == "TRK-1" and t1["status"] == "open"
    _, t2 = call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "Faster export", "type": "improvement"})
    _, w1 = call(base_url, "POST", "/api/projects/WEB/tickets", {"title": "Logo"})
    assert (t2["ref"], w1["ref"], w1["type"]) == ("TRK-2", "WEB-1", "task")

    _, projects = call(base_url, "GET", "/api/projects")
    counts = {p["key"]: p["counts"] for p in projects}
    assert counts == {"TRK": {"open": 2}, "WEB": {"open": 1}}


def test_duplicate_and_invalid_project_keys(base_url):
    call(base_url, "POST", "/api/projects", {"key": "ABC", "name": "A"})
    assert call(base_url, "POST", "/api/projects", {"key": "ABC", "name": "B"})[0] == 409
    assert call(base_url, "POST", "/api/projects", {"key": "1X", "name": "B"})[0] == 400
    assert call(base_url, "POST", "/api/projects", {"key": "OK", "name": ""})[0] == 400


def test_update_records_history_and_filters(base_url):
    call(base_url, "POST", "/api/projects", {"key": "TRK", "name": "T"})
    call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "A", "type": "bug", "labels": "UI, ui, api"})
    call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "B", "type": "improvement"})

    s, t = call(base_url, "PATCH", "/api/tickets/TRK-1", {"status": "in_progress", "priority": "high", "actor": "ed"})
    assert s == 200 and t["status"] == "in_progress" and t["labels"] == ["ui", "api"]
    change = t["comments"][-1]
    assert change["kind"] == "change" and change["author"] == "ed" and "status: open → in_progress" in change["body"]

    # a no-op patch doesn't add history
    _, t = call(base_url, "PATCH", "/api/tickets/TRK-1", {"status": "in_progress"})
    assert len(t["comments"]) == 1

    _, t = call(base_url, "POST", "/api/tickets/TRK-1/comments", {"body": "on it", "author": "ed"})
    assert t["comments"][-1]["body"] == "on it"

    _, rows = call(base_url, "GET", "/api/projects/TRK/tickets?status=in_progress")
    assert [r["ref"] for r in rows] == ["TRK-1"] and rows[0]["comment_count"] == 1
    _, rows = call(base_url, "GET", "/api/projects/TRK/tickets?type=improvement")
    assert [r["ref"] for r in rows] == ["TRK-2"]
    _, rows = call(base_url, "GET", "/api/projects/TRK/tickets?label=api")
    assert [r["ref"] for r in rows] == ["TRK-1"]
    _, rows = call(base_url, "GET", "/api/projects/TRK/tickets?q=B")
    assert [r["ref"] for r in rows] == ["TRK-2"]


def test_validation_and_not_found(base_url):
    call(base_url, "POST", "/api/projects", {"key": "TRK", "name": "T"})
    assert call(base_url, "POST", "/api/projects/TRK/tickets", {"title": ""})[0] == 400
    assert call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "x", "type": "nope"})[0] == 400
    assert call(base_url, "POST", "/api/projects/NOPE/tickets", {"title": "x"})[0] == 404
    assert call(base_url, "GET", "/api/tickets/TRK-99")[0] == 404
    assert call(base_url, "GET", "/api/tickets/garbage")[0] == 404


def test_delete_project_cascades(base_url):
    call(base_url, "POST", "/api/projects", {"key": "TRK", "name": "T"})
    call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "x"})
    assert call(base_url, "DELETE", "/api/projects/TRK")[0] == 200
    assert call(base_url, "GET", "/api/tickets/TRK-1")[0] == 404
    # key can be reused and numbering restarts
    call(base_url, "POST", "/api/projects", {"key": "TRK", "name": "T2"})
    assert call(base_url, "POST", "/api/projects/TRK/tickets", {"title": "y"})[1]["ref"] == "TRK-1"


def test_cross_origin_writes_rejected(base_url):
    s, _ = call(base_url, "POST", "/api/projects", {"key": "EVL", "name": "x"}, {"Origin": "http://evil.example"})
    assert s == 403


def test_serves_frontend(base_url):
    with urllib.request.urlopen(base_url + "/") as r:
        assert b"TrackAlong Tracker" in r.read()
    with urllib.request.urlopen(base_url + "/../server.py") as r:  # traversal falls back to index
        assert b"<!doctype html>" in r.read()
