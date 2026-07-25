"""
Request input limits — guard against runaway compute and malformed coordinates.

Limits are env-configurable so they can be tightened for a public deployment
without a code change.
"""
from __future__ import annotations

import math
import os
from typing import List

from fastapi import HTTPException

MAX_WAYPOINTS = int(os.getenv("MAX_WAYPOINTS", "100"))
MAX_ROUTE_KM = float(os.getenv("MAX_ROUTE_KM", "2000"))


def _haversine_km(a: List[float], b: List[float]) -> float:
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dphi = lat2 - lat1
    dlam = lon2 - lon1
    h = math.sin(dphi / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def route_length_km(waypoints: List[List[float]]) -> float:
    return sum(_haversine_km(waypoints[i - 1], waypoints[i]) for i in range(1, len(waypoints)))


def validate_waypoints(waypoints: List[List[float]]) -> float:
    """Validate count, coordinates, and total length. Returns the route length (km)."""
    if not waypoints or len(waypoints) < 2:
        raise HTTPException(status_code=422, detail="At least 2 waypoints required")
    if len(waypoints) > MAX_WAYPOINTS:
        raise HTTPException(
            status_code=422,
            detail=f"Too many waypoints: {len(waypoints)} (max {MAX_WAYPOINTS})",
        )
    for wp in waypoints:
        if len(wp) < 2:
            raise HTTPException(status_code=422, detail="Each waypoint must be [lat, lng]")
        lat, lng = wp[0], wp[1]
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            raise HTTPException(status_code=422, detail=f"Coordinate out of range: [{lat}, {lng}]")

    length = route_length_km(waypoints)
    if length > MAX_ROUTE_KM:
        raise HTTPException(
            status_code=422,
            detail=f"Route too long: {length:.0f} km (max {MAX_ROUTE_KM:.0f} km)",
        )
    return length
