from __future__ import annotations
from fastapi import APIRouter, HTTPException
from observability import log
from validation import validate_waypoints
from models.requests import OptimiseRouteRequest
from core.route_optimizer import optimise_corridor, CorridorParams

router = APIRouter()


@router.post("/optimise-route")
def optimise_route(req: OptimiseRouteRequest):
    validate_waypoints(req.waypoints)

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
    except Exception:
        log.exception("Route optimiser failed")
        raise HTTPException(status_code=500, detail="Route optimisation failed.")

    return {"waypoints": [[lat, lon] for lat, lon in result]}
