from __future__ import annotations
import pathlib
from fastapi import APIRouter, HTTPException
from models.requests import AnalyseRequest
from models.responses import (
    serialise_alignment, serialise_cant, serialise_costs,
    serialise_geology, serialise_land_zones,
)
from core.elevation import fetch_profile
from core.optimizer import optimise, GeometryParams
from core.cant import compute_radii, analyse_cant, detect_coincident_curves
from core.costing import estimate_costs, CostBands
from core.geology import fetch_geology
from core.land_zoning import analyse_land_zones

router = APIRouter()

_CACHE_DIR = pathlib.Path(__file__).parent.parent / "cache"
_CACHE_DIR.mkdir(exist_ok=True)


def _build_geom_params(p) -> GeometryParams:
    return GeometryParams(
        max_grade_pct=p.max_grade_pct,
        k_crest=p.k_crest,
        k_sag=p.k_sag,
        formation_width_m=p.formation_width_m,
        batter_cut=p.batter_cut,
        batter_fill=p.batter_fill,
        cut_trigger_m=p.cut_trigger_m,
        fill_trigger_m=p.fill_trigger_m,
        min_track_elev_m=p.min_track_elev_m,
        design_speed_kph=p.design_speed_kph,
        gauge_mm=p.gauge_mm,
        max_cant_mm=p.max_cant_mm,
        max_cant_deficiency_mm=p.max_cant_deficiency_mm,
        cant_gradient_max_mm_per_m=p.cant_gradient_max_mm_per_m,
        max_twist_mm_per_3m=p.max_twist_mm_per_3m,
        ruling_grade_length_km=p.ruling_grade_length_km,
    )


def _build_cost_bands(c) -> CostBands:
    return CostBands(**{k: v for k, v in c.model_dump().items()})


@router.post("/analyse")
def analyse(req: AnalyseRequest):
    if len(req.waypoints) < 2:
        raise HTTPException(status_code=422, detail="At least 2 waypoints required")

    try:
        profile = fetch_profile(req.waypoints)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Elevation fetch failed: {exc}")

    geom = _build_geom_params(req.params)

    geology = None
    if req.include_geology:
        try:
            geology = fetch_geology(profile, _CACHE_DIR / "geology")
        except Exception:
            pass  # non-fatal — analysis continues without geology data

    radii = compute_radii(profile)

    try:
        alignment = optimise(profile, geom, radii=radii, geology=geology)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Optimiser failed: {exc}")

    cant = analyse_cant(alignment.chainage, radii, geom)
    coincident = detect_coincident_curves(
        alignment.grade, alignment.chainage, radii, req.params.min_radius_m
    )

    land_zones = None
    if req.include_land_zones:
        route_latlng = [[p[1], p[2]] for p in profile.tolist()]
        try:
            land_zones = analyse_land_zones(
                route_latlng,
                corridor_m=req.corridor_m,
                category_costs=req.land_category_costs,
            )
        except Exception:
            pass

    cost_bands = _build_cost_bands(req.cost_bands)
    costs = estimate_costs(alignment, geology, cost_bands, double_track=req.double_track)

    route_length_km = float(profile[-1, 0]) / 1000.0

    return {
        "route_length_km": route_length_km,
        "alignment": serialise_alignment(alignment),
        "cant": serialise_cant(cant),
        "coincident_violations": [
            {"start_ch": v.start_ch, "end_ch": v.end_ch}
            for v in coincident
        ],
        "costs": serialise_costs(costs),
        "geology": serialise_geology(geology),
        "land_zones": serialise_land_zones(land_zones),
        "profile": {
            "chainage": profile[:, 0].tolist(),
            "lat": profile[:, 1].tolist(),
            "lng": profile[:, 2].tolist(),
            "ground_elev": profile[:, 3].tolist(),
        },
    }
