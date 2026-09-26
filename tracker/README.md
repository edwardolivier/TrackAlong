# TrackAlong Tracker

A small, locally hosted tracker for raising **bugs, improvements, features and tasks**
while you build — with support for **multiple projects**, each with its own ticket
numbering (`TRK-1`, `TRK-2`, `WEB-1`, …).

No dependencies beyond Python 3.11+ (standard library only). Data lives in a single
SQLite file.

## Run

```bash
python tracker/server.py
```

Then open <http://127.0.0.1:8765>. On Windows you can double-click `tracker/run.bat`;
on macOS/Linux run `tracker/run.sh`.

| Option   | Env var        | Default                   |
|----------|----------------|---------------------------|
| `--port` | `TRACKER_PORT` | `8765`                    |
| `--host` | `TRACKER_HOST` | `127.0.0.1`               |
| `--db`   | `TRACKER_DB`   | `tracker/data/tracker.db` |

The default database is git-ignored. Back it up by copying the `.db` file.

> **No login.** By default it only listens on `127.0.0.1` (this machine). If you use
> `--host 0.0.0.0` to share it on your network, anyone who can reach the port can
> read and edit tickets.

## Features

- **Projects** — create as many as you like; each has a short key used in ticket IDs.
  Deleting a project deletes all its tickets.
- **Tickets** — type (bug / improvement / feature / task), priority
  (low → critical), status, assignee, reporter, labels, description.
- **Board view** — kanban columns per status; drag a card to change its status.
- **List view** — table with filters for type, priority, status plus text search.
- **Ticket page** — inline editing, comments, and an automatic history of every
  field change (who changed what).
- **"You" box** (top right) — your name, remembered in the browser, used as the
  reporter / comment author / change author.

## Workflow

| Status      | Meaning                        |
|-------------|--------------------------------|
| Open        | Raised, not started            |
| In progress | Being worked on                |
| Blocked     | Waiting on something else      |
| In review   | Done, awaiting check / test    |
| Done        | Finished                       |
| Won't do    | Closed without doing it        |

## REST API

Everything the UI does is available as JSON under `/api` (writes need
`Content-Type: application/json`):

| Method | Path | |
|--------|------|-|
| GET/POST | `/api/projects` | list (with per-status counts) / create `{key, name, description}` |
| GET/PATCH/DELETE | `/api/projects/{KEY}` | |
| GET | `/api/projects/{KEY}/tickets?status=&type=&priority=&assignee=&label=&q=` | list / filter |
| POST | `/api/projects/{KEY}/tickets` | create `{title, type, priority, status, description, assignee, reporter, labels}` |
| GET/PATCH/DELETE | `/api/tickets/{KEY-N}` | PATCH accepts any ticket field plus `actor` (for history) |
| POST | `/api/tickets/{KEY-N}/comments` | `{body, author}` |
| GET | `/api/meta` | allowed types / statuses / priorities |

Example — raise a ticket from a script or CI job:

```bash
curl -X POST http://127.0.0.1:8765/api/projects/TRK/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title": "Export fails on empty route", "type": "bug", "priority": "high"}'
```

## Tests

```bash
pytest tests/test_tracker.py
```
