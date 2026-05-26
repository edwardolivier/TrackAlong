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

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
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
