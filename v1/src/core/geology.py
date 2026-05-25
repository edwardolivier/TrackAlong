"""
Geology fetch and engineering classification along a railway alignment.

Data source: Macrostrat API (v2.macrostrat.org) — free, no API key,
global coverage including Australia.

Map overlays (WMS — used in map.html, not here):
  GA national : https://services.ga.gov.au/gis/services/GA_Surface_Geology/MapServer/WMSServer
  QLD detail  : https://spatial-gis.information.qld.gov.au/arcgis/services/
                  GeoscientificInformation/GeologyRegional/MapServer/WMSServer

Engineering classification (AS 1726 / ISRM):
  A  Hard Rock   — UCS > 100 MPa   granite, basalt, gneiss, quartzite …
  B  Medium Rock — UCS 25-100 MPa  sandstone, limestone, schist …
  C  Weak Rock   — UCS 1-25 MPa    shale, mudstone, weathered rock …
  D  Soft Ground — UCS < 1 MPa     alluvium, clay, sand, colluvium …

Recommended cut/fill batter (H:V) per class (can be overridden by user):
  A: cut 0.50, fill 1.50
  B: cut 0.75, fill 1.75
  C: cut 1.50, fill 2.00
  D: cut 2.00, fill 2.50
"""

import json
import time
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable

import numpy as np
import requests

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engineering classification tables
# ---------------------------------------------------------------------------

_HARD_ROCK = {
    "granite", "granodiorite", "tonalite", "gabbro", "diorite", "norite",
    "gneiss", "quartzite", "basalt", "dolerite", "diabase", "rhyolite",
    "andesite", "dacite", "trachyte", "obsidian", "amphibolite",
    "hornblende", "migmatite", "eclogite", "dunite", "peridotite",
    "serpentinite", "intrusive", "plutonic",
    # GA standardised lithology terms
    "mafic", "felsic", "ultramafic",
}

_MEDIUM_ROCK = {
    "sandstone", "limestone", "dolomite", "dolostone", "calcarenite",
    "conglomerate", "breccia", "tuff", "ignimbrite", "greywacke",
    "wacke", "arkose", "chert", "ironstone", "quartzarenite",
    "calcilutite", "chalk", "travertine", "volcaniclastic",
    "phyllite", "schist", "slate", "argillite",
    # GA standardised lithology terms
    "siliciclastic", "carbonate", "mixed",
}

_WEAK_ROCK = {
    "shale", "mudstone", "siltstone", "mudrock", "claystone",
    "marl", "coal", "lignite", "carbonaceous", "black shale",
    "weathered", "laterite", "bauxite", "saprolite", "saprock",
    "duricrust",
    # GA standardised lithology terms
    "chemical",   # sedimentary chemical (evaporites etc.) — generally weak
}

_SOFT_GROUND = {
    "alluvium", "alluvial", "clay", "sand", "gravel", "silt", "mud",
    "colluvium", "peat", "soil", "fill", "talus", "scree", "rubble",
    "estuarine", "lacustrine", "fluvial", "aeolian", "eluvium",
    "swamp", "marsh", "bog",
    # GA uses "regolith" for surface deposits (sand plains, alluvium) — soft ground
    "regolith", "unconsolidated",
}

# Age terms implying soft ground regardless of lithology
_SOFT_AGES = {"holocene", "pleistocene", "quaternary", "recent"}

_ENG_COLORS = {
    "A": "#b91c1c",   # dark red — hard rock
    "B": "#c2410c",   # orange   — medium rock
    "C": "#a16207",   # amber    — weak rock
    "D": "#15803d",   # green    — soft ground
    "?": "#475569",   # slate    — unknown
}

_ENG_LABELS = {
    "A": "Hard Rock",
    "B": "Medium Rock",
    "C": "Weak Rock",
    "D": "Soft Ground",
    "?": "Unknown",
}

_ENG_BATTER = {
    "A": {"cut": 0.50, "fill": 1.50},
    "B": {"cut": 0.75, "fill": 1.75},
    "C": {"cut": 1.50, "fill": 2.00},
    "D": {"cut": 2.00, "fill": 2.50},
    "?": {"cut": 1.50, "fill": 2.00},   # conservative default
}

_ENG_RISKS = {
    "A": [],
    "B": ["Check for karst dissolution if limestone present",
          "Verify no significant jointing / faulting through cut"],
    "C": ["Swelling/slaking risk — drainage critical in cuts",
          "Slope monitoring recommended",
          "Design check required for cut heights > 10 m"],
    "D": ["Foundation treatment likely (surcharge, piling, or wick drains)",
          "Embankment settlement analysis required",
          "Slope stability — check fill embankment on soft base",
          "Shallow groundwater — dewatering may be needed"],
    "?": [],
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GeoPoint:
    """Geology at one sampled station."""
    chainage_m: float
    lat: float
    lng: float
    unit_name: str
    lithology: str
    age: str
    eng_class: str           # A / B / C / D / ?
    color: str
    source: str              # "macrostrat" | "cache" | "fallback"


@dataclass
class GeoSegment:
    """Merged geology segment for display."""
    start_ch: float
    end_ch: float
    unit_name: str
    lithology: str
    age: str
    eng_class: str
    eng_label: str
    color: str
    risk_notes: List[str] = field(default_factory=list)
    batter_cut: float = 1.5
    batter_fill: float = 2.0

    @property
    def length_m(self) -> float:
        return self.end_ch - self.start_ch


@dataclass
class GeologyResult:
    segments: List[GeoSegment]
    points: List[GeoPoint]
    batter_cut_array: np.ndarray    # per profile station
    batter_fill_array: np.ndarray   # per profile station
    any_data: bool = True

    @property
    def length_by_class(self):
        out = {k: 0.0 for k in "ABCD?"}
        for s in self.segments:
            out[s.eng_class] = out.get(s.eng_class, 0.0) + s.length_m
        return out

    @property
    def dominant_class(self) -> str:
        lbc = self.length_by_class
        return max(lbc, key=lbc.get)

    @property
    def risk_notes(self) -> List[str]:
        seen, out = set(), []
        for s in self.segments:
            for r in s.risk_notes:
                if r not in seen:
                    seen.add(r)
                    out.append(r)
        return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify(unit_name: str, lithology: str, age: str) -> str:
    """Return engineering class (A/B/C/D/?) from text fields."""
    text = (unit_name + " " + lithology + " " + age).lower()
    words = set(text.replace(",", " ").replace("/", " ").split())

    # Rock keywords take priority even for young ages (e.g. Holocene basalt is still hard rock)
    if words & _HARD_ROCK:
        return "A"
    if words & _MEDIUM_ROCK:
        return "B"

    # Age-based soft ground (only applied when no hard/medium rock keywords found)
    if words & _SOFT_AGES:
        return "D"

    if words & _SOFT_GROUND:
        return "D"
    if words & _WEAK_ROCK:
        return "C"

    # Partial matches for compound words (e.g. "feldspathic sandstone")
    for tok in words:
        for kw in _HARD_ROCK:
            if kw in tok:
                return "A"
        for kw in _MEDIUM_ROCK:
            if kw in tok:
                return "B"
        for kw in _WEAK_ROCK:
            if kw in tok:
                return "C"
        for kw in _SOFT_GROUND:
            if kw in tok:
                return "D"

    return "?"


# ---------------------------------------------------------------------------
# Macrostrat API
# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------

_TIMEOUT = 15   # seconds per request
_RETRY   = 2

# Primary: Geoscience Australia 1:1M Surface Geology (same data as the WMS overlay)
# Layer 11 = AUS_GA_1M_GUPoly_Lithology (polygon lithology classification)
_GA_URL = (
    "https://services.ga.gov.au/gis/rest/services/"
    "GA_Surface_Geology/MapServer/11/query"
)

# Fallback: Macrostrat (global, but currently has DNS/connectivity issues for some regions)
_MACROSTRAT_URL = "https://macrostrat.org/api/v2/geologic_units/map"


def _fetch_ga(lat: float, lng: float) -> dict | None:
    """
    Query Geoscience Australia 1:1M Surface Geology ArcGIS REST service.
    Returns parsed dict or None if no feature found (e.g. offshore or outside AU).
    """
    params = {
        "geometry":     f"{round(lng, 5)},{round(lat, 5)}",
        "geometryType": "esriGeometryPoint",
        "inSR":         "4326",
        "spatialRel":   "esriSpatialRelIntersects",
        "outFields":    "name,lithology,descr,geolhist",
        "returnGeometry": "false",
        "f":            "json",
    }
    r = requests.get(_GA_URL, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    features = data.get("features", [])
    if not features:
        return None
    attrs = features[0].get("attributes", {})
    name  = str(attrs.get("name")     or "")
    lith  = str(attrs.get("lithology") or "")   # GA standardised term, e.g. "sedimentary siliciclastic"
    age   = str(attrs.get("geolhist") or "")
    return {
        "unit_name": name,
        "lithology": lith,   # standardised term only — avoids "minor X" keywords in descriptions
        "age":       age,
        "color":     "#475569",
        "source":    "ga-geology",
    }


def _fetch_macrostrat(lat: float, lng: float) -> dict | None:
    """
    Query Macrostrat API as fallback. Returns parsed dict or None on failure.
    """
    params = {"lat": round(lat, 5), "lng": round(lng, 5)}
    try:
        r = requests.get(_MACROSTRAT_URL, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            items = data
        else:
            items = (data.get("success", {}).get("data", [])
                     or data.get("data", []) or [])
        if not items:
            return None
        item = items[0]
        lith = item.get("lith", "") or item.get("lithology", "") or ""
        if isinstance(lith, list):
            lith = ", ".join(
                (x.get("name", "") if isinstance(x, dict) else str(x))
                for x in lith
            )
        age = item.get("t_age", "") or item.get("age", "") or item.get("b_age", "")
        if isinstance(age, (int, float)):
            age = str(age) + " Ma"
        return {
            "unit_name": (item.get("unit_name", "") or item.get("name", "")
                          or item.get("strat_name", "")),
            "lithology": str(lith),
            "age":       str(age),
            "color":     item.get("color", "#475569") or "#475569",
            "source":    "macrostrat",
        }
    except Exception as exc:
        log.debug("Macrostrat fallback failed at (%.4f, %.4f): %s", lat, lng, exc)
        return None


def _fetch_one(lat: float, lng: float) -> dict:
    """
    Fetch surface geology at (lat, lng).
    Tries GA first (Australia-specific, reliable), then Macrostrat (global fallback).
    Returns a dict with keys: unit_name, lithology, age, color, source.
    """
    last_err = None
    for attempt in range(_RETRY):
        try:
            result = _fetch_ga(lat, lng)
            if result is not None:
                return result
            # Point outside GA coverage (offshore / outside Australia)
            log.debug("GA geology: no feature at (%.4f, %.4f) — trying Macrostrat", lat, lng)
            break
        except Exception as exc:
            last_err = exc
            log.debug("GA geology attempt %d/%d failed at (%.4f, %.4f): %s",
                      attempt + 1, _RETRY, lat, lng, exc)
            if attempt < _RETRY - 1:
                time.sleep(0.3)

    # Macrostrat fallback
    result = _fetch_macrostrat(lat, lng)
    if result is not None:
        return result

    if last_err:
        log.warning("Geology fetch failed at (%.4f, %.4f): %s", lat, lng, last_err)
    return {"unit_name": "", "lithology": "", "age": "",
            "color": "#475569", "source": "fallback"}


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def _cache_path(cache_dir: Path, lat: float, lng: float) -> Path:
    key = f"{lat:.2f}_{lng:.2f}"
    return cache_dir / f"geo_{key}.json"


def _load_cache(cache_dir: Path, lat: float, lng: float) -> Optional[dict]:
    p = _cache_path(cache_dir, lat, lng)
    if p.exists():
        try:
            with open(p) as f:
                d = json.load(f)
                d["source"] = "cache"
                return d
        except Exception:
            pass
    return None


def _save_cache(cache_dir: Path, lat: float, lng: float, data: dict):
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = _cache_path(cache_dir, lat, lng)
    try:
        with open(p, "w") as f:
            json.dump(data, f)
    except Exception as exc:
        log.debug("Could not save geology cache: %s", exc)


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

_SAMPLE_INTERVAL_M = 2000.0   # query Macrostrat every 2 km


def fetch_geology(profile: np.ndarray,
                  cache_dir: Path,
                  progress_callback: Optional[Callable] = None) -> GeologyResult:
    """
    profile : (N, 4) — chainage, lat, lng, elev
    Returns GeologyResult with per-station batter arrays.
    """
    chainage = profile[:, 0]
    lats     = profile[:, 1]
    lons     = profile[:, 2]
    n        = len(chainage)

    # Sample points at SAMPLE_INTERVAL_M along the route
    total      = float(chainage[-1] - chainage[0])
    n_samples  = max(2, int(total / _SAMPLE_INTERVAL_M) + 1)
    sample_chs = np.linspace(float(chainage[0]), float(chainage[-1]), n_samples)
    sample_lats = np.interp(sample_chs, chainage, lats)
    sample_lons = np.interp(sample_chs, chainage, lons)

    geo_cache_dir = cache_dir / "geology"

    # --- Parallel fetch with cache ---
    def fetch_with_cache(i):
        slat = float(sample_lats[i])
        slng = float(sample_lons[i])
        cached = _load_cache(geo_cache_dir, slat, slng)
        if cached:
            return i, slat, slng, cached
        data = _fetch_one(slat, slng)
        if data["source"] == "macrostrat":
            _save_cache(geo_cache_dir, slat, slng, data)
        return i, slat, slng, data

    results_raw = [None] * n_samples
    n_done = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_with_cache, i): i for i in range(n_samples)}
        for fut in as_completed(futures):
            idx, slat, slng, data = fut.result()
            results_raw[idx] = (sample_chs[idx], slat, slng, data)
            n_done += 1
            if progress_callback:
                pct = int(n_done / n_samples * 100)
                progress_callback(pct, f"Geology: {n_done}/{n_samples} points fetched…")

    # --- Build GeoPoints ---
    geo_points: List[GeoPoint] = []
    for ch, slat, slng, d in results_raw:
        if d is None:
            continue
        ec = classify(d["unit_name"], d["lithology"], d["age"])
        geo_points.append(GeoPoint(
            chainage_m=float(ch),
            lat=slat, lng=slng,
            unit_name=d["unit_name"],
            lithology=d["lithology"],
            age=d["age"],
            eng_class=ec,
            color=_ENG_COLORS[ec],
            source=d["source"],
        ))

    any_data = any(
        p.unit_name or p.lithology for p in geo_points
    )

    sources = [p.source for p in geo_points]
    n_live   = sources.count("macrostrat")
    n_cached = sources.count("cache")
    n_empty  = sources.count("macrostrat-empty")
    n_fail   = sources.count("fallback")
    log.info(
        "Geology fetch complete: %d pts — %d live, %d cached, %d empty, %d failed; any_data=%s",
        len(geo_points), n_live, n_cached, n_empty, n_fail, any_data
    )

    # --- Merge consecutive same-class points into segments ---
    segments: List[GeoSegment] = []
    if geo_points:
        seg_start = geo_points[0]
        seg_pts   = [geo_points[0]]

        def _flush(pts, end_ch):
            p0 = pts[0]
            ec = p0.eng_class
            bt = _ENG_BATTER[ec]
            segments.append(GeoSegment(
                start_ch=p0.chainage_m,
                end_ch=end_ch,
                unit_name=p0.unit_name or "—",
                lithology=p0.lithology or "—",
                age=p0.age or "—",
                eng_class=ec,
                eng_label=_ENG_LABELS[ec],
                color=_ENG_COLORS[ec],
                risk_notes=_ENG_RISKS[ec],
                batter_cut=bt["cut"],
                batter_fill=bt["fill"],
            ))

        for pt in geo_points[1:]:
            if pt.eng_class == seg_pts[-1].eng_class:
                seg_pts.append(pt)
            else:
                _flush(seg_pts, pt.chainage_m)
                seg_pts = [pt]
        _flush(seg_pts, float(chainage[-1]))

    # Default segment if no data
    if not segments:
        segments = [GeoSegment(
            start_ch=float(chainage[0]),
            end_ch=float(chainage[-1]),
            unit_name="Unknown",
            lithology="Unknown",
            age="—",
            eng_class="?",
            eng_label="Unknown",
            color=_ENG_COLORS["?"],
            risk_notes=[],
            batter_cut=1.5,
            batter_fill=2.0,
        )]

    # --- Build per-station batter arrays ---
    batter_cut_arr  = np.full(n, 1.5)
    batter_fill_arr = np.full(n, 2.0)

    for seg in segments:
        mask = (chainage >= seg.start_ch) & (chainage <= seg.end_ch)
        batter_cut_arr[mask]  = seg.batter_cut
        batter_fill_arr[mask] = seg.batter_fill

    return GeologyResult(
        segments=segments,
        points=geo_points,
        batter_cut_array=batter_cut_arr,
        batter_fill_array=batter_fill_arr,
        any_data=any_data,
    )
