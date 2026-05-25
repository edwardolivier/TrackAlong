"""
Land acquisition zoning analysis — OpenStreetMap data source.

Fetches land-use polygons from the OSM Overpass API, buffers the route
corridor, intersects with those polygons, classifies each OSM tag into a
cost category, and returns total land acquisition cost estimates.

Results are cached to disk (cache/land_zones/) so the same bounding box
is only fetched once.

Requires: geopandas, shapely, requests  (all already in requirements.txt)
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

_CACHE_DIR = Path(__file__).parent.parent.parent / "cache" / "land_zones"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# ── Default cost categories (AUD / m²) ──────────────────────────────────────

DEFAULT_CATEGORY_COSTS: Dict[str, float] = {
    "Crown / Conservation": 0.0,
    "Rural / Agricultural": 3.0,
    "Residential (low density)": 200.0,
    "Residential (med/high density)": 400.0,
    "Commercial": 350.0,
    "Industrial": 180.0,
    "Infrastructure": 50.0,
    "Other": 30.0,
}

# ── OSM tag → cost category ──────────────────────────────────────────────────

_LANDUSE_MAP: Dict[str, str] = {
    # Crown / Conservation
    "conservation":           "Crown / Conservation",
    "forest":                 "Crown / Conservation",
    "nature_reserve":         "Crown / Conservation",
    "recreation_ground":      "Crown / Conservation",
    "village_green":          "Crown / Conservation",
    "cemetery":               "Crown / Conservation",
    "grass":                  "Crown / Conservation",
    # Rural
    "farmland":               "Rural / Agricultural",
    "farm":                   "Rural / Agricultural",
    "meadow":                 "Rural / Agricultural",
    "orchard":                "Rural / Agricultural",
    "vineyard":               "Rural / Agricultural",
    "allotments":             "Rural / Agricultural",
    "greenhouse_horticulture":"Rural / Agricultural",
    "plant_nursery":          "Rural / Agricultural",
    "scrub":                  "Rural / Agricultural",
    # Residential
    "residential":            "Residential (low density)",
    # Commercial
    "commercial":             "Commercial",
    "retail":                 "Commercial",
    "mixed":                  "Commercial",
    # Industrial
    "industrial":             "Industrial",
    "port":                   "Industrial",
    "quarry":                 "Industrial",
    # Infrastructure
    "military":               "Infrastructure",
    "railway":                "Infrastructure",
    "aeroway":                "Infrastructure",
    "depot":                  "Infrastructure",
}

_NATURAL_MAP: Dict[str, str] = {
    "wood":       "Crown / Conservation",
    "scrub":      "Crown / Conservation",
    "heath":      "Crown / Conservation",
    "grassland":  "Crown / Conservation",
    "water":      "Crown / Conservation",
    "wetland":    "Crown / Conservation",
    "beach":      "Crown / Conservation",
    "mud":        "Crown / Conservation",
    "sand":       "Crown / Conservation",
    "reef":       "Crown / Conservation",
}

_LEISURE_MAP: Dict[str, str] = {
    "park":             "Crown / Conservation",
    "nature_reserve":   "Crown / Conservation",
    "recreation_ground":"Crown / Conservation",
    "garden":           "Crown / Conservation",
    "common":           "Crown / Conservation",
    "golf_course":      "Rural / Agricultural",
    "sports_centre":    "Infrastructure",
    "stadium":          "Infrastructure",
}


def _classify_osm_tags(tags: dict) -> str:
    """Map an OSM tag dict to a cost category."""
    lu = tags.get("landuse", "")
    if lu and lu in _LANDUSE_MAP:
        return _LANDUSE_MAP[lu]

    nat = tags.get("natural", "")
    if nat and nat in _NATURAL_MAP:
        return _NATURAL_MAP[nat]

    lei = tags.get("leisure", "")
    if lei and lei in _LEISURE_MAP:
        return _LEISURE_MAP[lei]

    boundary = tags.get("boundary", "")
    if boundary in ("protected_area", "national_park"):
        return "Crown / Conservation"

    return "Other"


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class LandZoneArea:
    category: str
    area_m2: float
    cost_per_m2: float
    subtotal: float


@dataclass
class LandZoneSegment:
    start_ch_m: float
    end_ch_m: float
    category: str


@dataclass
class LandZoneResult:
    zones: List[LandZoneArea]
    total_area_m2: float
    total_cost: float
    corridor_width_m: float
    data_source: str   # "OpenStreetMap" or custom label
    segments: List[LandZoneSegment] = field(default_factory=list)


# ── OSM data fetch ────────────────────────────────────────────────────────────

def _fetch_osm_polygons(bbox, timeout: int = 60) -> List[dict]:
    """
    Query Overpass API for landuse / natural / leisure closed ways within bbox.
    bbox: (south, west, north, east).
    Returns list of {"tags": {...}, "coords": [(lon, lat), ...]}.
    Cached to disk by bbox hash.
    """
    cache_key  = hashlib.md5(json.dumps(bbox).encode()).hexdigest()
    cache_file = _CACHE_DIR / f"osm_{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    south, west, north, east = bbox
    bbox_str = f"{south},{west},{north},{east}"
    query = (
        f"[out:json][timeout:{timeout}];\n"
        f"(\n"
        f'  way["landuse"]({bbox_str});\n'
        f'  way["natural"]["natural"!="coastline"]({bbox_str});\n'
        f'  way["leisure"]({bbox_str});\n'
        f'  way["boundary"~"protected_area|national_park"]({bbox_str});\n'
        f");\n"
        f"out geom;\n"
    )

    _HEADERS = {"User-Agent": "TrackAlong/1.0 (railway alignment analyser)"}
    for attempt in range(3):
        try:
            r = requests.post(
                _OVERPASS_URL,
                data={"data": query},   # Overpass requires form field named "data"
                headers=_HEADERS,
                timeout=timeout + 15,
            )
            r.raise_for_status()
            data = r.json()
            break
        except Exception as exc:
            if attempt == 2:
                raise ConnectionError(
                    f"Overpass API unavailable after 3 attempts: {exc}"
                ) from exc
            time.sleep(5 * (attempt + 1))

    elements = []
    for elem in data.get("elements", []):
        if elem.get("type") != "way":
            continue
        geom = elem.get("geometry", [])
        if len(geom) < 3:
            continue
        # Only closed ways form valid polygons
        if abs(geom[0]["lat"] - geom[-1]["lat"]) > 1e-7 or \
           abs(geom[0]["lon"] - geom[-1]["lon"]) > 1e-7:
            continue
        coords = [(g["lon"], g["lat"]) for g in geom]   # shapely (x=lon, y=lat)
        elements.append({"tags": elem.get("tags", {}), "coords": coords})

    cache_file.write_text(json.dumps(elements))
    return elements


# ── Main analysis function ────────────────────────────────────────────────────

def analyse_land_zones(
    route_latlng: List,
    corridor_m: float = 30.0,
    category_costs: Optional[Dict[str, float]] = None,
    progress_callback=None,
) -> LandZoneResult:
    """
    Fetch OSM land-use data along the route, intersect with the buffered
    corridor, and return per-category area and cost estimates.

    route_latlng : [[lat, lng], ...] waypoints
    corridor_m   : total corridor width in metres (buffered corridor_m/2 each side)
    category_costs: override $/m² rates; uses DEFAULT_CATEGORY_COSTS if None
    progress_callback: optional callable(str) for status messages
    """
    import geopandas as gpd
    from shapely.geometry import LineString, Polygon

    if category_costs is None:
        category_costs = DEFAULT_CATEGORY_COSTS.copy()

    def _prog(msg):
        if progress_callback:
            progress_callback(msg)

    # ── Route geometry ───────────────────────────────────────────────────────
    coords = [(float(p[1]), float(p[0])) for p in route_latlng]
    line   = LineString(coords)
    route_gdf = gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326")

    # ── Fetch OSM data ───────────────────────────────────────────────────────
    lats = [p[0] for p in route_latlng]
    lngs = [p[1] for p in route_latlng]
    pad  = 0.05   # ~5 km padding around bounding box
    bbox = (min(lats) - pad, min(lngs) - pad, max(lats) + pad, max(lngs) + pad)

    _prog("Fetching OSM land-use data…")
    elements = _fetch_osm_polygons(bbox)

    _empty = LandZoneResult(
        zones=[], total_area_m2=0.0, total_cost=0.0,
        corridor_width_m=corridor_m, data_source="OpenStreetMap",
    )

    if not elements:
        return _empty

    # ── Build GeoDataFrame from OSM elements ─────────────────────────────────
    _prog("Classifying land zones…")
    geoms, cats = [], []
    for elem in elements:
        try:
            poly = Polygon(elem["coords"])
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            geoms.append(poly)
            cats.append(_classify_osm_tags(elem["tags"]))
        except Exception:
            continue

    if not geoms:
        return _empty

    zones_gdf = gpd.GeoDataFrame(
        {"category": cats, "geometry": geoms}, crs="EPSG:4326"
    )

    # ── Reproject to metric CRS ──────────────────────────────────────────────
    try:
        route_proj = route_gdf.to_crs("EPSG:9473")   # GDA2020 Albers
    except Exception:
        route_proj = route_gdf.to_crs("EPSG:3577")   # GDA94 Albers fallback
    target_crs = route_proj.crs

    corridor_geom = route_proj.geometry.buffer(corridor_m / 2.0)
    corridor_gdf  = gpd.GeoDataFrame(geometry=corridor_geom, crs=target_crs)
    zones_proj    = zones_gdf.to_crs(target_crs)

    # ── Intersect corridor with zones ────────────────────────────────────────
    _prog("Computing land corridor intersection…")
    minx, miny, maxx, maxy = corridor_gdf.total_bounds
    zones_clip = zones_proj.cx[minx:maxx, miny:maxy].copy()

    if zones_clip.empty:
        return _empty

    intersection = gpd.overlay(
        corridor_gdf[["geometry"]],
        zones_clip,
        how="intersection",
        keep_geom_type=False,
    )

    if intersection.empty:
        return _empty

    intersection["area_m2"] = intersection.geometry.area
    grouped = intersection.groupby("category")["area_m2"].sum()

    # ── Build result ─────────────────────────────────────────────────────────
    result_zones: List[LandZoneArea] = []
    for cat, area in grouped.items():
        cost_per_m2 = category_costs.get(cat, DEFAULT_CATEGORY_COSTS["Other"])
        result_zones.append(LandZoneArea(
            category=cat,
            area_m2=float(area),
            cost_per_m2=cost_per_m2,
            subtotal=float(area) * cost_per_m2,
        ))

    result_zones.sort(key=lambda z: z.subtotal, reverse=True)

    # ── Chainage segments for profile strip ──────────────────────────────────
    seg_list: List[LandZoneSegment] = []
    try:
        from shapely.strtree import STRtree
        line = route_proj.geometry.iloc[0]
        total_m = line.length
        n_samples = max(2, min(400, int(total_m / 100) + 1))
        sample_ds = [total_m * i / (n_samples - 1) for i in range(n_samples)]

        zone_geoms_list = list(zones_clip.geometry)
        zone_cats_list  = list(zones_clip["category"])
        tree = STRtree(zone_geoms_list)

        half_w = corridor_m / 2.0
        sample_cats = []
        for d in sample_ds:
            pt_buf = line.interpolate(d).buffer(half_w)
            idxs   = tree.query(pt_buf, predicate="intersects")
            if len(idxs) == 0:
                sample_cats.append("Other")
            else:
                best = max(idxs,
                           key=lambda i: category_costs.get(zone_cats_list[int(i)], 30.0))
                sample_cats.append(zone_cats_list[int(best)])

        for i, cat in enumerate(sample_cats):
            start = float(sample_ds[i])
            end   = float(sample_ds[i + 1]) if i + 1 < len(sample_ds) else float(total_m)
            if seg_list and seg_list[-1].category == cat:
                seg_list[-1].end_ch_m = end
            else:
                seg_list.append(LandZoneSegment(start, end, cat))
    except Exception:
        seg_list = []

    return LandZoneResult(
        zones=result_zones,
        total_area_m2=sum(z.area_m2 for z in result_zones),
        total_cost=sum(z.subtotal for z in result_zones),
        corridor_width_m=corridor_m,
        data_source="OpenStreetMap",
        segments=seg_list,
    )
