"""
Saved routes — server-side persistence of a user's waypoints + parameters.

This is the web equivalent of v1's local "Save/Load route JSON". Records are stored
as JSON blobs at routes/<user>/<id>.json via the pluggable storage backend (local
directory in dev, GCS in production). Each handler is scoped to the authenticated user.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from storage import get_storage

router = APIRouter()
_store = get_storage()

# Route ids we generate are 32-char hex; reject anything else so a crafted id can't
# escape the user's prefix (path traversal) in the local backend.
_ID_RE = re.compile(r"^[a-f0-9]{32}$")


class SavedRoutePayload(BaseModel):
    name: str
    waypoints: List[List[float]]
    params: Optional[dict] = None
    cost_bands: Optional[dict] = None
    corridor: Optional[dict] = None


def _key(user: str, route_id: str) -> str:
    return f"routes/{user}/{route_id}.json"


def _valid_id(route_id: str) -> str:
    if not _ID_RE.match(route_id):
        raise HTTPException(status_code=400, detail="Invalid route id")
    return route_id


@router.post("/routes")
def save_route(body: SavedRoutePayload, user: str = Depends(current_user)) -> dict:
    if len(body.waypoints) < 2:
        raise HTTPException(status_code=422, detail="A route needs at least 2 waypoints")
    route_id = uuid.uuid4().hex
    record: dict[str, Any] = {
        "id": route_id,
        "name": body.name,
        "waypoints": body.waypoints,
        "params": body.params,
        "cost_bands": body.cost_bands,
        "corridor": body.corridor,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _store.write_json(_key(user, route_id), record)
    return {"id": route_id, "name": body.name, "created_at": record["created_at"]}


@router.get("/routes")
def list_routes(user: str = Depends(current_user)) -> dict:
    out = []
    for key in _store.list(f"routes/{user}/"):
        rec = _store.read_json(key)
        if not rec:
            continue
        out.append({
            "id": rec.get("id"),
            "name": rec.get("name"),
            "created_at": rec.get("created_at"),
            "n_waypoints": len(rec.get("waypoints") or []),
        })
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"routes": out}


@router.get("/routes/{route_id}")
def get_route(route_id: str, user: str = Depends(current_user)) -> dict:
    rec = _store.read_json(_key(user, _valid_id(route_id)))
    if not rec:
        raise HTTPException(status_code=404, detail="Route not found")
    return rec


@router.delete("/routes/{route_id}")
def delete_route(route_id: str, user: str = Depends(current_user)) -> dict:
    if not _store.delete(_key(user, _valid_id(route_id))):
        raise HTTPException(status_code=404, detail="Route not found")
    return {"deleted": route_id}
