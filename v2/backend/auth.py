from __future__ import annotations
import os
from fastapi import Request, HTTPException, Depends
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
_ALLOWED_EMAILS = set(filter(None, os.getenv("ALLOWED_EMAILS", "").split(",")))
_DEV_MODE = os.getenv("DEV_MODE", "").lower() == "true"


async def verify_google_token(request: Request) -> dict:
    if _DEV_MODE:
        return {"email": "dev@localhost", "sub": "dev"}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")

    token = auth_header[7:]
    try:
        info = id_token.verify_oauth2_token(
            token, google_requests.Request(), _CLIENT_ID
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

    if _ALLOWED_EMAILS and info.get("email") not in _ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Email not authorised")

    return info
