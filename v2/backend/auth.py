"""
Authentication for the single-operator deployment.

One account, credentials supplied entirely via environment (no hardcoded defaults):
  SECRET_KEY         — HMAC signing key for the session JWT   (required)
  APP_USERNAME       — the single login name                  (default: "admin")
  APP_PASSWORD_HASH  — argon2 hash of the password            (required)
  TOKEN_EXPIRE_HOURS — session lifetime in hours              (default: 8)

The app refuses to start if SECRET_KEY or APP_PASSWORD_HASH is unset, so it can
never fall back to a guessable password. Generate the hash with:
    python scripts/hash_password.py

Multi-user accounts (registration, a user table, roles) are deferred to the public
phase; for now this gates the tool to its owner.
"""
from __future__ import annotations
import os
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Request, HTTPException, Depends


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Environment variable {name!r} is required but not set. "
            "Refusing to start without it — see auth.py for the required config."
        )
    return val


_SECRET = _require("SECRET_KEY")
_USERNAME = os.getenv("APP_USERNAME", "admin")
_PASSWORD_HASH = _require("APP_PASSWORD_HASH")
_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "8"))

_ph = PasswordHasher()


def create_token(username: str) -> str:
    payload = {"sub": username, "exp": time.time() + _EXPIRE_HOURS * 3600}
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def login(username: str, password: str) -> str:
    # Constant-ish response: verify the hash even on username mismatch is overkill
    # for a single account, but we still avoid leaking which field was wrong.
    if username != _USERNAME:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    try:
        _ph.verify(_PASSWORD_HASH, password)
    except (VerifyMismatchError, InvalidHashError):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return create_token(username)


async def verify_token(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return jwt.decode(auth[7:], _SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def current_user(payload: dict = Depends(verify_token)) -> str:
    """FastAPI dependency: the authenticated username (JWT subject)."""
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token")
    return sub
