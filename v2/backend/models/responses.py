from __future__ import annotations
import math
import numpy as np
from typing import Any


def _safe(v: Any) -> Any:
    """Recursively convert numpy types and non-finite floats to JSON-safe values."""
    if isinstance(v, np.ndarray):
        return [_safe(x) for x in v.tolist()]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        v = float(v)
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, list):
        return [_safe(x) for x in v]
    if isinstance(v, dict):
        return {k: _safe(val) for k, val in v.items()}
    return v


def serialise_alignment(al) -> dict:
    return {
        "chainage": _safe(al.chainage),
        "ground": _safe(al.ground),
        "track": _safe(al.track),
        "cut": _safe(al.cut),
        "fill": _safe(al.fill),
        "grade": _safe(al.grade),
        "total_cut_m3": _safe(al.total_cut_m3),
        "total_fill_m3": _safe(al.total_fill_m3),
        "max_grade_pct": _safe(al.max_grade_pct),
        "ruling_grade_pct": _safe(al.ruling_grade_pct),
        "geology_adjusted_cut_m3": _safe(al.geology_adjusted_cut_m3),
        "geology_adjusted_fill_m3": _safe(al.geology_adjusted_fill_m3),
        "geology_applied": al.geology_applied,
        "grade_compensation_applied": al.grade_compensation_applied,
        "tunnels": [
            {
                "index": s.index, "kind": s.kind,
                "start_ch": s.start_ch, "end_ch": s.end_ch,
                "length_m": s.length_m, "max_depth": s.max_depth,
            }
            for s in al.tunnels
        ],
        "bridges": [
            {
                "index": s.index, "kind": s.kind,
                "start_ch": s.start_ch, "end_ch": s.end_ch,
                "length_m": s.length_m, "max_depth": s.max_depth,
            }
            for s in al.bridges
        ],
        "violations": [
            {"chainage": _safe(v[0]), "grade": _safe(v[1])}
            for v in (al.violations or [])
        ],
    }


def serialise_cant(ca) -> dict:
    return {
        "chainage": _safe(ca.chainage),
        "radii": _safe(ca.radii),
        "equilibrium_cant": _safe(ca.equilibrium_cant),
        "actual_cant": _safe(ca.actual_cant),
        "cant_deficiency": _safe(ca.cant_deficiency),
        "max_speed": _safe(ca.max_speed),
        "design_speed_kph": ca.design_speed_kph,
        "min_speed_kph": ca.min_speed_kph,
        "speed_restricted_stations": ca.speed_restricted_stations,
        "twist_violation_stations": ca.twist_violation_stations,
        "transition_violation_count": ca.transition_violation_count,
        "reverse_violation_count": ca.reverse_violation_count,
        "curves": [
            {
                "start_ch": _safe(c.start_ch), "end_ch": _safe(c.end_ch),
                "radius_m": _safe(c.radius_m),
            }
            for c in (ca.curves or [])
        ],
    }


def serialise_costs(cr) -> dict:
    def lines(lst):
        return [
            {"label": l.label, "quantity": _safe(l.quantity),
             "unit": l.unit, "rate": _safe(l.rate), "subtotal": _safe(l.subtotal)}
            for l in lst
        ]
    return {
        "lines_cut": lines(cr.lines_cut),
        "lines_fill": lines(cr.lines_fill),
        "lines_bridges": lines(cr.lines_bridges),
        "lines_tunnels": lines(cr.lines_tunnels),
        "lines_track": lines(cr.lines_track),
        "lines_systems": lines(cr.lines_systems),
        "subtotal_cut": _safe(cr.subtotal_cut),
        "subtotal_fill": _safe(cr.subtotal_fill),
        "subtotal_earthworks": _safe(cr.subtotal_earthworks),
        "subtotal_bridges": _safe(cr.subtotal_bridges),
        "subtotal_tunnels": _safe(cr.subtotal_tunnels),
        "subtotal_track": _safe(cr.subtotal_track),
        "subtotal_systems": _safe(cr.subtotal_systems),
        "subtotal_base": _safe(cr.subtotal_base),
        "contingency_amount": _safe(cr.contingency_amount),
        "total": _safe(cr.total),
        "contingency_pct": cr.contingency_pct,
        "route_length_km": _safe(cr.route_length_km),
        "double_track": cr.double_track,
    }


def serialise_geology(geo) -> dict | None:
    if geo is None or not geo.any_data:
        return None
    return {
        "dominant_class": geo.dominant_class,
        "length_by_class": geo.length_by_class,
        "risk_notes": geo.risk_notes,
        "segments": [
            {"start_ch": _safe(s.start_ch), "end_ch": _safe(s.end_ch),
             "eng_class": s.eng_class, "eng_label": s.eng_label,
             "unit_name": s.unit_name, "lithology": s.lithology}
            for s in (geo.segments or [])
        ],
    }


def serialise_land_zones(lz) -> dict | None:
    if lz is None:
        return None
    return {
        "total_area_m2": _safe(lz.total_area_m2),
        "total_cost": _safe(lz.total_cost),
        "corridor_width_m": lz.corridor_width_m,
        "data_source": lz.data_source,
        "zones": [
            {"category": z.category, "area_m2": _safe(z.area_m2),
             "cost": _safe(z.cost)}
            for z in (lz.zones or [])
        ],
    }
