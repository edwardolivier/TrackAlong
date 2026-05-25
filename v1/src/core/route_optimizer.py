"""
Horizontal route corridor optimizer.

Searches a lateral grid of candidate waypoints between start and end
using forward dynamic programming on a layered directed acyclic graph.

Algorithm:
  1. Build a grid of N intermediate layers, each with M lateral candidate
     positions spanning ±corridor_km perpendicular to the direct line.
  2. Batch-fetch ground elevation at all grid nodes in one API call.
  3. Score each edge (adjacent layer pair) by: route length + grade-excess
     penalty (terrain steeper than max_grade signals future earthwork).
  4. DP forward pass finds the minimum-cost path end-to-end.
  5. Return the winning (lat, lon) waypoint sequence.

For multi-segment routes (3+ user waypoints) each consecutive pair is
optimised independently and the segments are concatenated.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable

from .elevation import fetch_point_elevations

_R = 6_371_000.0  # Earth radius (m)


# ---------------------------------------------------------------------------
# Coordinate helpers (no external deps — avoids pyproj version issues)
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2.0 * _R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    x = math.sin(dlam) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    return math.degrees(math.atan2(x, y)) % 360.0


def _offset_point(lat: float, lon: float, bearing_deg: float, dist_m: float) -> Tuple[float, float]:
    """Rhumb-line offset — accurate enough for corridor widths ≤ 100 km."""
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    d_R = dist_m / _R
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d_R)
        + math.cos(lat1) * math.sin(d_R) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(d_R) * math.cos(lat1),
        math.cos(d_R) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

@dataclass
class CorridorParams:
    corridor_km: float = 30.0    # ± half-width perpendicular to direct line
    num_layers: int = 8          # intermediate waypoint columns
    lateral_steps: int = 7       # candidates per column (odd → centre = direct line)
    weight_length: float = 1.0   # cost per km of segment length
    weight_grade: float = 5.0    # extra cost per km when grade exceeds max_grade


# Intensity presets: (num_layers, lateral_steps)
INTENSITY = {
    "Low (fast)":    (5,  5),
    "Medium":        (8,  7),
    "High (thorough)": (12, 9),
}

# Objective presets: (weight_length, weight_grade)
OBJECTIVE = {
    "Shortest path":      (1.0, 0.3),
    "Balanced":           (1.0, 5.0),
    "Minimise earthwork": (0.4, 15.0),
}


# ---------------------------------------------------------------------------
# Grid construction
# ---------------------------------------------------------------------------

def _build_grid(
    start_ll: Tuple[float, float],
    end_ll: Tuple[float, float],
    params: CorridorParams,
) -> List[List[Tuple[float, float]]]:
    """
    Returns a list of layers:
      grid[0]     = [start_point]
      grid[1..N]  = params.lateral_steps candidate positions each
      grid[N+1]   = [end_point]
    """
    lat1, lon1 = start_ll
    lat2, lon2 = end_ll
    total_dist = _haversine_m(lat1, lon1, lat2, lon2)
    fwd_bearing = _initial_bearing(lat1, lon1, lat2, lon2)
    perp_bearing = (fwd_bearing + 90.0) % 360.0

    n = params.num_layers
    m = params.lateral_steps
    half = m // 2
    corridor_m = params.corridor_km * 1000.0
    step_m = corridor_m / max(half, 1)

    grid: List[List[Tuple[float, float]]] = [[(lat1, lon1)]]

    for layer in range(1, n + 1):
        frac = layer / (n + 1)
        lat_c, lon_c = _offset_point(lat1, lon1, fwd_bearing, frac * total_dist)

        layer_pts: List[Tuple[float, float]] = []
        for j in range(m):
            offset_m = (j - half) * step_m
            if abs(offset_m) < 1.0:
                layer_pts.append((lat_c, lon_c))
            else:
                lat_j, lon_j = _offset_point(lat_c, lon_c, perp_bearing, offset_m)
                layer_pts.append((lat_j, lon_j))
        grid.append(layer_pts)

    grid.append([(lat2, lon2)])
    return grid


# ---------------------------------------------------------------------------
# Edge cost
# ---------------------------------------------------------------------------

def _edge_cost(
    lat_a: float, lon_a: float, elev_a: float,
    lat_b: float, lon_b: float, elev_b: float,
    max_grade_pct: float,
    params: CorridorParams,
) -> float:
    dist_m = _haversine_m(lat_a, lon_a, lat_b, lon_b)
    if dist_m < 1.0:
        return 0.0
    dist_km = dist_m / 1000.0

    grade = abs(elev_b - elev_a) / dist_m   # fractional grade
    max_grade = max_grade_pct / 100.0

    # Deeply infeasible: terrain far steeper than max grade in both directions
    if grade > max_grade * 3.0:
        return 1e12

    # Base: distance cost
    cost = params.weight_length * dist_km

    # Grade-excess penalty: terrain steeper than max grade signals earthwork
    if grade > max_grade:
        excess_ratio = (grade - max_grade) / max_grade   # 0 at limit, 1 at 2× limit
        cost += params.weight_grade * excess_ratio * dist_km

    return cost


# ---------------------------------------------------------------------------
# Single-segment corridor optimizer
# ---------------------------------------------------------------------------

def _optimise_segment(
    start_ll: Tuple[float, float],
    end_ll: Tuple[float, float],
    params: CorridorParams,
    max_grade_pct: float,
    progress_cb: Optional[Callable[[str], None]],
) -> List[Tuple[float, float]]:
    grid = _build_grid(start_ll, end_ll, params)
    n_layers = len(grid)

    # Collect all unique grid nodes for elevation batch fetch
    all_pts = list({pt for layer in grid for pt in layer})

    if progress_cb:
        progress_cb(f"Fetching terrain elevations ({len(all_pts)} grid nodes)…")

    elevs = fetch_point_elevations(all_pts)

    if progress_cb:
        progress_cb("Searching optimal corridor path…")

    INF = 1e18
    best = [[INF] * len(grid[i]) for i in range(n_layers)]
    best[0][0] = 0.0
    parent: List[List[Optional[int]]] = [[None] * len(grid[i]) for i in range(n_layers)]

    for layer in range(n_layers - 1):
        for ci, cur_pt in enumerate(grid[layer]):
            if best[layer][ci] >= INF:
                continue
            cur_elev = elevs.get(cur_pt, 0.0)

            for ni, nxt_pt in enumerate(grid[layer + 1]):
                nxt_elev = elevs.get(nxt_pt, 0.0)
                ec = _edge_cost(
                    cur_pt[0], cur_pt[1], cur_elev,
                    nxt_pt[0], nxt_pt[1], nxt_elev,
                    max_grade_pct, params,
                )
                new_cost = best[layer][ci] + ec
                if new_cost < best[layer + 1][ni]:
                    best[layer + 1][ni] = new_cost
                    parent[layer + 1][ni] = ci

    # Backtrack from end node (always index 0 — single point)
    path = [0] * n_layers
    idx = 0
    for layer in range(n_layers - 1, 0, -1):
        path[layer] = idx
        idx = parent[layer][idx] if parent[layer][idx] is not None else 0
    path[0] = 0

    return [grid[layer][path[layer]] for layer in range(n_layers)]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def optimise_corridor(
    waypoints: List[List[float]],
    params: CorridorParams,
    max_grade_pct: float,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> List[Tuple[float, float]]:
    """
    Find the optimal corridor between each consecutive pair of waypoints.

    waypoints : list of [lat, lon] pairs (at least 2).
    Returns a flat list of (lat, lon) tuples for the optimised route,
    including the original start and end points.
    """
    if len(waypoints) < 2:
        return [(w[0], w[1]) for w in waypoints]

    segments = len(waypoints) - 1
    all_pts: List[Tuple[float, float]] = []

    for seg_idx in range(segments):
        start_ll = (float(waypoints[seg_idx][0]), float(waypoints[seg_idx][1]))
        end_ll = (float(waypoints[seg_idx + 1][0]), float(waypoints[seg_idx + 1][1]))

        def _cb(msg: str, _s: int = seg_idx) -> None:
            if progress_cb:
                progress_cb(f"Segment {_s + 1}/{segments}: {msg}")

        seg_pts = _optimise_segment(start_ll, end_ll, params, max_grade_pct, _cb)

        if all_pts:
            seg_pts = seg_pts[1:]   # drop duplicate start (= previous segment's end)
        all_pts.extend(seg_pts)

    return all_pts
