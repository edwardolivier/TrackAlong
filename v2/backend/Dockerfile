# Build context must be the repo root:
#   docker build -f v2/backend/Dockerfile .

FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY v2/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Core analysis library (shared from v1 — single source of truth)
COPY v1/src/core ./core

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
