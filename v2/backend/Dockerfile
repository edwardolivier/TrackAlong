# Build context must be the repo root:
#   docker build -f v2/backend/Dockerfile .

FROM python:3.11-slim

WORKDIR /app

# Core analysis package (shared from v1 — single source of truth for analysis logic
# AND its dependencies). Installing it as a package means `import core` resolves the
# same way here as it does in local dev and CI.
COPY pyproject.toml ./pyproject.toml
COPY v1/src/core ./v1/src/core
RUN pip install --no-cache-dir .

# Web-layer dependencies (FastAPI, auth, etc.)
COPY v2/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend application
COPY v2/backend/main.py ./main.py
COPY v2/backend/auth.py ./auth.py
COPY v2/backend/models ./models
COPY v2/backend/api ./api

# React build is copied here by CI (v2/frontend/dist → static/)
# If absent at runtime, the API still works; only the SPA is missing.
COPY v2/frontend/dist ./static

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
