from __future__ import annotations
import os
import time
import jwt
from fastapi import Request, HTTPException

_SECRET = os.getenv("SECRET_KEY", "trackalong-dev-secret")
_USERNAME = os.getenv("APP_USERNAME", "admin")
_PASSWORD = os.getenv("APP_PASSWORD", "adminadmin")
_EXPIRE_HOURS = 8


def create_token(username: str) -> str:
    payload = {"sub": username, "exp": time.time() + _EXPIRE_HOURS * 3600}
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def login(username: str, password: str) -> str:
    if username != _USERNAME or password != _PASSWORD:
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
