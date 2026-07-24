from __future__ import annotations
import os
import pathlib
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth import verify_token, login
from api.analyse import router as analyse_router
from api.optimise_route import router as optimise_router

app = FastAPI(title="TrackAlong API", version="2.0.0")

# Explicit origin allowlist — never the "*" + credentials combination (invalid per the
# CORS spec and rejected by browsers). In production the SPA is served same-origin, so
# CORS mainly matters for local dev (Vite on :5173 proxying to the API on :8080).
_DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:5173"
_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public endpoints
@app.get("/health")
def health():
    return {"status": "ok"}


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
def auth_login(req: LoginRequest):
    token = login(req.username, req.password)
    return {"token": token}


# Protected API routes
_auth = [Depends(verify_token)]
app.include_router(analyse_router, prefix="/api", dependencies=_auth)
app.include_router(optimise_router, prefix="/api", dependencies=_auth)

# Serve React build
_static = pathlib.Path(__file__).parent / "static"
if _static.exists():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        return FileResponse(_static / "index.html")
