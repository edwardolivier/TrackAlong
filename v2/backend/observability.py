"""
Logging, request context, and optional error tracking.

- configure_logging(): structured logs to stdout (Cloud Run captures stdout).
- RequestContextMiddleware: assigns a short request id, echoes it as X-Request-ID,
  and logs one line per request with method, path, status, and duration.
- init_sentry(): optional — only active if SENTRY_DSN is set and sentry-sdk is installed.
"""
from __future__ import annotations

import logging
import os
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger("trackalong")


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. under a reloader)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(handler)
    root.setLevel(level)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            dur = (time.perf_counter() - start) * 1000
            log.exception("rid=%s %s %s -> ERROR (%.0fms)",
                          rid, request.method, request.url.path, dur)
            raise
        dur = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        log.info("rid=%s %s %s -> %s (%.0fms)",
                 rid, request.method, request.url.path, response.status_code, dur)
        return response


def init_sentry() -> None:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=dsn,
            environment=os.getenv("ENV", "production"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        )
        log.info("Sentry error tracking initialised")
    except Exception as exc:  # pragma: no cover - depends on optional dep
        log.warning("SENTRY_DSN is set but Sentry could not initialise: %s", exc)
