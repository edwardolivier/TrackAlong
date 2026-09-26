"""
TrackAlong Tracker — a small, locally hosted ticket / improvement tracker.

Supports multiple projects, each with its own ticket sequence (e.g. TRK-1, TRK-2,
WEB-1). Standard library only: `http.server` for serving, `sqlite3` for storage,
so it runs anywhere Python 3.11+ is installed with no `pip install`.

    python tracker/server.py                       # http://127.0.0.1:8765
    python tracker/server.py --port 9000 --db ~/tickets.db
    python tracker/server.py --host 0.0.0.0        # share on your LAN (no auth!)
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
DEFAULT_DB = HERE / "data" / "tracker.db"

TYPES = ("bug", "improvement", "feature", "task")
STATUSES = ("open", "in_progress", "blocked", "review", "done", "wont_do")
PRIORITIES = ("low", "medium", "high", "critical")
PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
TICKET_REF_RE = re.compile(r"^([A-Z][A-Z0-9]{1,9})-(\d+)$")
MAX_BODY = 1_000_000  # bytes

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    next_number INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    number      INTEGER NOT NULL,
    type        TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',
    priority    TEXT NOT NULL DEFAULT 'medium',
    assignee    TEXT NOT NULL DEFAULT '',
    reporter    TEXT NOT NULL DEFAULT '',
    labels      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (project_id, number)
);
CREATE TABLE IF NOT EXISTS comments (
    id         INTEGER PRIMARY KEY,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author     TEXT NOT NULL DEFAULT '',
    body       TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'comment',  -- 'comment' | 'change'
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_project ON tickets(project_id);
CREATE INDEX IF NOT EXISTS idx_comments_ticket ON comments(ticket_id);
"""


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
class Store:
    """All database access. One connection, serialised by a lock (plenty for local use)."""

    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    # -- helpers ------------------------------------------------------------ #
    def _project_row(self, key: str) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM projects WHERE key = ?", (key,)).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, f"project {key} not found")
        return row

    def _ticket_row(self, ref: str) -> sqlite3.Row:
        m = TICKET_REF_RE.match(ref)
        if not m:
            raise ApiError(HTTPStatus.NOT_FOUND, f"ticket {ref} not found")
        row = self.conn.execute(
            "SELECT t.*, p.key AS project_key FROM tickets t JOIN projects p ON p.id = t.project_id "
            "WHERE p.key = ? AND t.number = ?",
            (m.group(1), int(m.group(2))),
        ).fetchone()
        if row is None:
            raise ApiError(HTTPStatus.NOT_FOUND, f"ticket {ref} not found")
        return row

    @staticmethod
    def _ticket_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["ref"] = f"{d['project_key']}-{d['number']}"
        d["labels"] = [x for x in d["labels"].split(",") if x]
        d.pop("project_id", None)
        return d

    # -- projects ----------------------------------------------------------- #
    def list_projects(self) -> list[dict]:
        with self.lock:
            projects = [dict(r) for r in self.conn.execute("SELECT * FROM projects ORDER BY name")]
            counts = self.conn.execute(
                "SELECT project_id, status, COUNT(*) AS n FROM tickets GROUP BY project_id, status"
            ).fetchall()
        by_id: dict[int, dict] = {}
        for c in counts:
            by_id.setdefault(c["project_id"], {})[c["status"]] = c["n"]
        for p in projects:
            p["counts"] = by_id.get(p["id"], {})
            p.pop("next_number")
        return projects

    def get_project(self, key: str) -> dict:
        with self.lock:
            p = dict(self._project_row(key))
        p.pop("next_number")
        return p

    def create_project(self, data: dict) -> dict:
        key = str(data.get("key", "")).strip().upper()
        name = _text(data, "name", required=True, max_len=120)
        if not PROJECT_KEY_RE.match(key):
            raise ApiError(
                HTTPStatus.BAD_REQUEST,
                "key must be 2-10 characters: a letter followed by letters/digits (e.g. TRK)",
            )
        with self.lock:
            try:
                self.conn.execute(
                    "INSERT INTO projects (key, name, description, created_at) VALUES (?, ?, ?, ?)",
                    (key, name, _text(data, "description", max_len=5000), now()),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                raise ApiError(HTTPStatus.CONFLICT, f"project key {key} already exists")
        return self.get_project(key)

    def update_project(self, key: str, data: dict) -> dict:
        fields = {}
        if "name" in data:
            fields["name"] = _text(data, "name", required=True, max_len=120)
        if "description" in data:
            fields["description"] = _text(data, "description", max_len=5000)
        with self.lock:
            row = self._project_row(key)
            if fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                self.conn.execute(f"UPDATE projects SET {sets} WHERE id = ?", (*fields.values(), row["id"]))
                self.conn.commit()
        return self.get_project(key)

    def delete_project(self, key: str) -> None:
        with self.lock:
            row = self._project_row(key)
            self.conn.execute("DELETE FROM projects WHERE id = ?", (row["id"],))
            self.conn.commit()

    # -- tickets ------------------------------------------------------------ #
    def list_tickets(self, key: str, filters: dict[str, str]) -> list[dict]:
        sql = (
            "SELECT t.*, p.key AS project_key, "
            "(SELECT COUNT(*) FROM comments c WHERE c.ticket_id = t.id AND c.kind = 'comment') AS comment_count "
            "FROM tickets t JOIN projects p ON p.id = t.project_id WHERE p.key = ?"
        )
        args: list = [key]
        for col in ("status", "type", "priority", "assignee"):
            if filters.get(col):
                sql += f" AND t.{col} = ?"
                args.append(filters[col])
        if filters.get("q"):
            sql += " AND (t.title LIKE ? OR t.description LIKE ? OR t.labels LIKE ?)"
            like = f"%{filters['q']}%"
            args += [like, like, like]
        if filters.get("label"):
            sql += " AND (',' || t.labels || ',') LIKE ?"
            args.append(f"%,{filters['label']},%")
        sql += " ORDER BY t.number DESC"
        with self.lock:
            self._project_row(key)
            rows = self.conn.execute(sql, args).fetchall()
        return [self._ticket_dict(r) for r in rows]

    def get_ticket(self, ref: str) -> dict:
        with self.lock:
            t = self._ticket_dict(self._ticket_row(ref))
            t["comments"] = [
                dict(c)
                for c in self.conn.execute(
                    "SELECT id, author, body, kind, created_at FROM comments WHERE ticket_id = ? ORDER BY id",
                    (t["id"],),
                )
            ]
        return t

    def create_ticket(self, key: str, data: dict) -> dict:
        fields = _ticket_fields(data, creating=True)
        with self.lock:
            project = self._project_row(key)
            number = project["next_number"]
            ts = now()
            self.conn.execute(
                "INSERT INTO tickets (project_id, number, type, title, description, status, priority, "
                "assignee, reporter, labels, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    project["id"], number, fields["type"], fields["title"], fields.get("description", ""),
                    fields.get("status", "open"), fields.get("priority", "medium"),
                    fields.get("assignee", ""), fields.get("reporter", ""), fields.get("labels", ""), ts, ts,
                ),
            )
            self.conn.execute("UPDATE projects SET next_number = ? WHERE id = ?", (number + 1, project["id"]))
            self.conn.commit()
        return self.get_ticket(f"{key}-{number}")

    def update_ticket(self, ref: str, data: dict) -> dict:
        actor = _text(data, "actor", max_len=80)
        fields = _ticket_fields(data, creating=False)
        with self.lock:
            row = self._ticket_row(ref)
            changed = {k: v for k, v in fields.items() if row[k] != v}
            changes = [
                "description edited" if k == "description" else f"{k}: {_show(row[k])} → {_show(v)}"
                for k, v in changed.items()
            ]
            if changed:
                ts = now()
                sets = ", ".join(f"{k} = ?" for k in changed)
                self.conn.execute(
                    f"UPDATE tickets SET {sets}, updated_at = ? WHERE id = ?", (*changed.values(), ts, row["id"])
                )
                self.conn.execute(
                    "INSERT INTO comments (ticket_id, author, body, kind, created_at) VALUES (?, ?, ?, 'change', ?)",
                    (row["id"], actor, "; ".join(changes), ts),
                )
                self.conn.commit()
        return self.get_ticket(ref)

    def delete_ticket(self, ref: str) -> None:
        with self.lock:
            row = self._ticket_row(ref)
            self.conn.execute("DELETE FROM tickets WHERE id = ?", (row["id"],))
            self.conn.commit()

    def add_comment(self, ref: str, data: dict) -> dict:
        body = _text(data, "body", required=True, max_len=20000)
        author = _text(data, "author", max_len=80)
        with self.lock:
            row = self._ticket_row(ref)
            ts = now()
            self.conn.execute(
                "INSERT INTO comments (ticket_id, author, body, kind, created_at) VALUES (?, ?, ?, 'comment', ?)",
                (row["id"], author, body, ts),
            )
            self.conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (ts, row["id"]))
            self.conn.commit()
        return self.get_ticket(ref)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _text(data: dict, name: str, *, required: bool = False, max_len: int = 200) -> str:
    value = data.get(name, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be a string")
    value = value.strip()
    if required and not value:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} is required")
    if len(value) > max_len:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be at most {max_len} characters")
    return value


def _choice(data: dict, name: str, options: tuple[str, ...]) -> str:
    value = data.get(name)
    if value not in options:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} must be one of: {', '.join(options)}")
    return value


def _labels(value) -> str:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ApiError(HTTPStatus.BAD_REQUEST, "labels must be a list of strings")
    cleaned = []
    for label in value:
        label = label.strip().lower()
        if label and label not in cleaned:
            cleaned.append(label[:40])
    return ",".join(cleaned[:20])


def _ticket_fields(data: dict, *, creating: bool) -> dict:
    out: dict = {}
    if creating or "title" in data:
        out["title"] = _text(data, "title", required=True, max_len=200)
    if creating or "type" in data:
        out["type"] = _choice(data, "type", TYPES) if "type" in data else "task"
    for name, options in (("status", STATUSES), ("priority", PRIORITIES)):
        if name in data:
            out[name] = _choice(data, name, options)
    if "description" in data:
        out["description"] = _text(data, "description", max_len=50000)
    for name in ("assignee", "reporter"):
        if name in data:
            out[name] = _text(data, name, max_len=80)
    if "labels" in data:
        out["labels"] = _labels(data["labels"])
    return out


def _show(value: str) -> str:
    return value if value else "(none)"


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TrackAlongTracker/1.0"

        def log_message(self, fmt, *args):  # quieter default logging
            if os.environ.get("TRACKER_QUIET") != "1":
                super().log_message(fmt, *args)

        # -- dispatch ------------------------------------------------------- #
        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _dispatch(self, method: str):
            url = urlparse(self.path)
            try:
                if not url.path.startswith("/api/"):
                    if method != "GET":
                        raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
                    return self._static(url.path)
                if method != "GET":
                    self._check_same_origin()
                parts = [p for p in url.path[len("/api/"):].split("/") if p]
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                status, payload = self._route(method, parts, query)
                self._json(status, payload)
            except ApiError as e:
                self._json(e.status, {"error": e.message})
            except Exception:  # never leak internals to the client
                self.log_error("unhandled error on %s %s", method, self.path)
                import traceback

                traceback.print_exc()
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal server error"})

        def _route(self, method: str, parts: list[str], query: dict):
            match (method, parts):
                case ("GET", ["meta"]):
                    return 200, {"types": TYPES, "statuses": STATUSES, "priorities": PRIORITIES}
                case ("GET", ["projects"]):
                    return 200, store.list_projects()
                case ("POST", ["projects"]):
                    return 201, store.create_project(self._body())
                case ("GET", ["projects", key]):
                    return 200, store.get_project(key)
                case ("PATCH", ["projects", key]):
                    return 200, store.update_project(key, self._body())
                case ("DELETE", ["projects", key]):
                    store.delete_project(key)
                    return 200, {"ok": True}
                case ("GET", ["projects", key, "tickets"]):
                    return 200, store.list_tickets(key, query)
                case ("POST", ["projects", key, "tickets"]):
                    return 201, store.create_ticket(key, self._body())
                case ("GET", ["tickets", ref]):
                    return 200, store.get_ticket(ref)
                case ("PATCH", ["tickets", ref]):
                    return 200, store.update_ticket(ref, self._body())
                case ("DELETE", ["tickets", ref]):
                    store.delete_ticket(ref)
                    return 200, {"ok": True}
                case ("POST", ["tickets", ref, "comments"]):
                    return 201, store.add_comment(ref, self._body())
            raise ApiError(HTTPStatus.NOT_FOUND, "not found")

        # -- helpers -------------------------------------------------------- #
        def _check_same_origin(self):
            # Blocks other websites open in your browser from writing to the tracker.
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                raise ApiError(HTTPStatus.FORBIDDEN, "cross-origin request rejected")
            if "application/json" not in (self.headers.get("Content-Type") or "") and self.command != "DELETE":
                raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body too large")
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ApiError(HTTPStatus.BAD_REQUEST, "invalid JSON body")
            if not isinstance(data, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
            return data

        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            if not target.is_relative_to(STATIC_DIR) or not target.is_file():
                target = STATIC_DIR / "index.html"  # SPA fallback
            body = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def make_server(host: str, port: int, db_path: str | Path) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(Store(db_path)))


def main() -> None:
    parser = argparse.ArgumentParser(description="TrackAlong local ticket tracker")
    parser.add_argument("--host", default=os.environ.get("TRACKER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("TRACKER_PORT", "8765")))
    parser.add_argument("--db", default=os.environ.get("TRACKER_DB", str(DEFAULT_DB)))
    args = parser.parse_args()

    httpd = make_server(args.host, args.port, args.db)
    print(f"TrackAlong Tracker running at http://{args.host}:{args.port}  (db: {args.db})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
