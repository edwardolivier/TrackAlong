"""
Elevation data service. Fetches SRTM elevation with local disk caching.

API priority:
  1. Open-Meteo  (https://api.open-meteo.com/v1/elevation)
     — no API key, no strict rate limit, 100 locations / request
  2. OpenTopoData SRTM30m  (https://api.opentopodata.org/v1/srtm30m)
     — no API key, ~1 req/s rate limit, 100 locations / request

Results are cached to disk so a route is only fetched once.
"""

import json
import math
import hashlib
import time
from pathlib import Path
import numpy as np
import requests
from scipy.interpolate import CubicSpline

CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "elevation"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_OPENMETEO_URL    = "https://api.open-meteo.com/v1/elevation"
_OPENTOPODATA_URL = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE = 100   # safe for both APIs


# ── Geometry helpers ─────────────────────────────────────────────────────────

def _haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _interpolate_points_along_polyline(waypoints, interval_m):
    if len(waypoints) < 2:
        return waypoints, [0.0]

    cum = [0.0]
    for i in range(1, len(waypoints)):
        cum.append(cum[-1] + _haversine_m(*waypoints[i - 1], *waypoints[i]))

    total = cum[-1]
    lats = [p[0] for p in waypoints]
    lngs = [p[1] for p in waypoints]

    from scipy.interpolate import interp1d
    f_lat = interp1d(cum, lats, kind="linear")
    f_lng = interp1d(cum, lngs, kind="linear")

    distances = list(np.arange(0, total, interval_m))
    if not distances or distances[-1] < total - 0.1:
        distances.append(total)

    sampled = [[float(f_lat(d)), float(f_lng(d))] for d in distances]
    return sampled, distances


# ── Caching ──────────────────────────────────────────────────────────────────

def _cache_key(locations):
    payload = json.dumps(locations, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()


# ── API calls ────────────────────────────────────────────────────────────────

def _call_openmeteo(locations):
    """Open-Meteo elevation: GET with comma-separated lat/lng lists."""
    lats = ",".join(str(l["latitude"])  for l in locations)
    lngs = ",".join(str(l["longitude"]) for l in locations)
    r = requests.get(
        _OPENMETEO_URL,
        params={"latitude": lats, "longitude": lngs},
        timeout=45,
    )
    r.raise_for_status()
    elev = r.json().get("elevation")
    if not elev or len(elev) != len(locations):
        raise ValueError("Unexpected Open-Meteo response shape")
    return elev


def _call_opentopodata(locations):
    """OpenTopoData SRTM30m: GET with pipe-separated lat,lng pairs."""
    loc_str = "|".join(f"{l['latitude']},{l['longitude']}" for l in locations)
    r = requests.get(
        _OPENTOPODATA_URL,
        params={"locations": loc_str},
        timeout=45,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK":
        raise ValueError(f"OpenTopoData returned status: {data.get('status')}")
    return [pt["elevation"] for pt in data["results"]]


def _fetch_elevations_api(locations):
    """
    Fetch elevations for a batch of {latitude, longitude} dicts.
    Tries Open-Meteo first, then OpenTopoData. Caches to disk.
    """
    cache_file = CACHE_DIR / (_cache_key(locations) + ".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    # --- Primary: Open-Meteo ---
    last_exc = None
    for attempt in range(3):
        try:
            elev = _call_openmeteo(locations)
            cache_file.write_text(json.dumps(elev))
            return elev
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)

    # --- Fallback: OpenTopoData ---
    for attempt in range(3):
        try:
            time.sleep(1.1)   # respect ~1 req/s rate limit
            elev = _call_opentopodata(locations)
            cache_file.write_text(json.dumps(elev))
            return elev
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(2 ** attempt)

    raise ConnectionError(
        f"All elevation APIs failed. Last error: {last_exc}\n"
        "Check your internet connection, or the route may be in an area "
        "not covered by the elevation APIs."
    )


# ── Public interface ──────────────────────────────────────────────────────────

def fetch_profile(waypoints, query_interval_m=100, output_interval_m=10,
                  progress_callback=None):
    """
    Return ndarray (N, 4) — chainage_m, lat, lng, ground_elev_m — sampled
    every *output_interval_m* metres along the route.

    Queries the API at *query_interval_m* spacing, then cubic-spline
    interpolates down to *output_interval_m*.
    """
    sampled_points, distances = _interpolate_points_along_polyline(
        waypoints, query_interval_m
    )

    locs = [{"latitude": p[0], "longitude": p[1]} for p in sampled_points]

    elevations = []
    total_batches = math.ceil(len(locs) / BATCH_SIZE)
    for i in range(0, len(locs), BATCH_SIZE):
        batch      = locs[i: i + BATCH_SIZE]
        batch_elev = _fetch_elevations_api(batch)
        elevations.extend(batch_elev)
        if progress_callback:
            done = i + len(batch)
            progress_callback(
                int(50 * done / len(locs)),
                f"Fetching elevation: {done}/{len(locs)} points…"
            )

    cs_elev    = CubicSpline(distances, elevations)
    total_dist = distances[-1]

    fine_distances = list(np.arange(0, total_dist, output_interval_m))
    if not fine_distances or fine_distances[-1] < total_dist - 0.1:
        fine_distances.append(total_dist)
    fine_distances = np.array(fine_distances)

    fine_elevs = cs_elev(fine_distances)

    from scipy.interpolate import interp1d
    all_lats = [p[0] for p in sampled_points]
    all_lngs = [p[1] for p in sampled_points]
    f_lat    = interp1d(distances, all_lats)
    f_lng    = interp1d(distances, all_lngs)
    fine_lats = f_lat(fine_distances)
    fine_lngs = f_lng(fine_distances)

    if progress_callback:
        progress_callback(50, "Elevation profile ready.")

    return np.column_stack([fine_distances, fine_lats, fine_lngs, fine_elevs])


def fetch_point_elevations(points):
    """
    Fetch elevation for a list of (lat, lon) tuples.
    Returns dict {(lat, lon): elevation_m}.
    """
    if not points:
        return {}

    result   = {}
    pts_list = list(points)
    for i in range(0, len(pts_list), BATCH_SIZE):
        batch_pts  = pts_list[i: i + BATCH_SIZE]
        batch_locs = [{"latitude": p[0], "longitude": p[1]} for p in batch_pts]
        elevs      = _fetch_elevations_api(batch_locs)
        for pt, elev in zip(batch_pts, elevs):
            result[pt] = float(elev)
    return result
