# TrackAlong v2 — Web App

FastAPI backend + React frontend, containerised for Google Cloud Run.

> **Status:** In development. Working toward feature parity with the v1 desktop app.

## Stack

- **Backend:** FastAPI (Python) — wraps the v1 core analysis library (`v1/src/core`, packaged as `trackalong-core`) as a REST API
- **Frontend:** React + Leaflet + Plotly.js
- **Auth:** single-operator username/password → HS256 JWT (see below). Multi-user accounts are planned for a later public phase.
- **Hosting:** Google Cloud Run
- **CI/CD:** GitHub Actions — tests on every push/PR, deploys to Cloud Run on push to `main`

## Configuration (backend environment)

The backend refuses to start unless the secrets are set — there are no insecure defaults.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SECRET_KEY` | **yes** | — | HMAC key that signs the session JWT |
| `APP_PASSWORD_HASH` | **yes** | — | argon2 hash of the login password |
| `APP_USERNAME` | no | `admin` | the single login name |
| `TOKEN_EXPIRE_HOURS` | no | `8` | session lifetime |
| `ALLOWED_ORIGINS` | no | localhost dev origins | comma-separated CORS allowlist |

Generate the password hash (plaintext is never stored):

```bash
cd v2/backend
python scripts/hash_password.py   # prints APP_PASSWORD_HASH
```

In production these are provided as GitHub Actions secrets (`SECRET_KEY`, `APP_PASSWORD_HASH`, `APP_USERNAME`) and injected into Cloud Run by the deploy workflow. Moving them to Secret Manager is a planned hardening step.

## Development

From the repo root:

```bash
# 1. Install the shared core library (editable) + backend deps
pip install -e .
pip install -r v2/backend/requirements-dev.txt

# 2. Backend (http://localhost:8080)
cd v2/backend
python scripts/hash_password.py    # enter a dev password, copy the printed hash
export SECRET_KEY=dev-secret
export APP_PASSWORD_HASH='<paste the hash from above>'
uvicorn main:app --reload --port 8080

# 3. Frontend (http://localhost:5173, proxies /api and /health to :8080)
cd v2/frontend
npm ci
npm run dev
```

## Tests

```bash
pip install -e . -r v2/backend/requirements-dev.txt
pytest            # backend + core
cd v2/frontend && npm run build   # frontend build gate
```
