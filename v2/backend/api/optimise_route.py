from __future__ import annotations
from fastapi import APIRouter, HTTPException
from models.requests import OptimiseRouteRequest
from core.route_optimizer import optimise_corridor, CorridorParams

router = APIRouter()


@router.post("/optimise-route")
def optimise_route(req: OptimiseRouteRequest):
    if len(req.waypoints) < 2:
        raise HTTPException(status_code=422, detail="At least 2 waypoints required")

    corridor = CorridorParams(
        corridor_km=req.corridor.corridor_km,
        num_layers=req.corridor.num_layers,
        lateral_steps=req.corridor.lateral_steps,
        weight_length=req.corridor.weight_length,
        weight_grade=req.corridor.weight_grade,
    )

    try:
        result = optimise_corridor(
            req.waypoints, corridor, req.params.max_grade_pct
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Route optimiser failed: {exc}")

    return {"waypoints": [[lat, lon] for lat, lon in result]}
