"""
Vertical alignment optimiser.

Pipeline:
  1. Run LP on an adaptive coarse grid (spacing driven by K-value) so the
     solver only decides grade at genuine control points, not every 10 m.
  2. Extract VIPs from the coarse LP result (where grade changes).
  3. Evaluate proper parabolic vertical curves at each VIP across the fine
     10 m grid — this is standard railway design, not a post-process hack.
  4. Detect tunnel / bridge sections and compute earthwork volumes.
  5. Apply grade compensation on sharp curves (ARTC: ΔG = 600/R %).
  6. Compute ruling grade over the specified window.

Structure rules:
  cut  > cut_trigger_m  → tunnel  (earthwork volume excluded, structure logged)
  fill > fill_trigger_m → bridge  (earthwork volume excluded, structure logged)

Formation level:
  The grade line is treated as formation level (top of subgrade /
  underside of ballast).  Earthwork cut/fill is measured from here.
"""

import numpy as np
from scipy.optimize import linprog
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GeometryParams:
    max_grade_pct: float       # e.g. 1.0 means 1 %
    k_crest: float             # vertical curve K-value for crests
    k_sag: float               # vertical curve K-value for sags
    formation_width_m: float
    batter_cut: float          # horizontal : vertical (e.g. 1.5 → 1.5H:1V)
    batter_fill: float
    cut_trigger_m: float = 50.0
    fill_trigger_m: float = 10.0
    min_track_elev_m: float = -1e9
    # Speed & cant parameters
    design_speed_kph: float = 115.0
    gauge_mm: float = 1435.0
    max_cant_mm: float = 100.0
    max_cant_deficiency_mm: float = 75.0
    cant_gradient_max_mm_per_m: float = 2.25
    max_twist_mm_per_3m: float = 7.0
    ruling_grade_length_km: float = 10.0


@dataclass
class Structure:
    index: int
    kind: str           # "tunnel" or "bridge"
    start_ch: float
    end_ch: float
    max_depth: float

    @property
    def length_m(self) -> float:
        return self.end_ch - self.start_ch


@dataclass
class VerticalAlignment:
    chainage: np.ndarray
    ground: np.ndarray
    track: np.ndarray
    cut: np.ndarray
    fill: np.ndarray
    grade: np.ndarray
    total_cut_m3: float
    total_fill_m3: float
    max_grade_pct: float
    violations: List[Tuple]
    tunnels: List[Structure] = field(default_factory=list)
    bridges: List[Structure] = field(default_factory=list)
    min_track_elev_m: float = -1e9
    ruling_grade_pct: float = 0.0
    grade_compensation_applied: bool = False
    coincident_curve_violations: List[Tuple] = field(default_factory=list)
    geology_adjusted_cut_m3: float = 0.0
    geology_adjusted_fill_m3: float = 0.0
    geology_applied: bool = False

    @property
    def num_tunnels(self) -> int:  return len(self.tunnels)

    @property
    def num_bridges(self) -> int:  return len(self.bridges)

    @property
    def total_tunnel_length_m(self) -> float:
        return sum(t.length_m for t in self.tunnels)

    @property
    def total_bridge_length_m(self) -> float:
        return sum(b.length_m for b in self.bridges)

    @property
    def total_tunnel_volume_m3(self) -> float:
        return self.total_tunnel_length_m * 50.0

    @property
    def total_bridge_volume_m3(self) -> float:
        return self.total_bridge_length_m * 5.0


# ---------------------------------------------------------------------------
# LP grade line
# ---------------------------------------------------------------------------

def _lp_grade_line(ground: np.ndarray, chainage: np.ndarray,
                   max_grade_pct: float,
                   min_track_elev: float = -1e9,
                   max_grade_array: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Minimise Σ(cut_i + fill_i) subject to gradient constraints.
    max_grade_array: per-interval grade limit (fraction/m).  If None,
    the scalar max_grade_pct is used uniformly.
    """
    n = len(ground)
    N = 3 * n
    max_grade_scalar = max_grade_pct / 100.0

    c_obj = np.zeros(N)
    c_obj[n: 2 * n] = 1.0
    c_obj[2 * n:]   = 1.0

    d = np.diff(chainage)
    n_grade = 2 * (n - 1)
    A_ub = np.zeros((n_grade, N))
    b_ub = np.zeros(n_grade)

    for i in range(n - 1):
        di = d[i]
        limit = (float(max_grade_array[i]) if max_grade_array is not None
                 else max_grade_scalar)
        limit = max(limit, 1e-4)   # safety floor
        A_ub[2 * i,     i]     =  1.0 / di
        A_ub[2 * i,     i + 1] = -1.0 / di
        b_ub[2 * i]            =  limit
        A_ub[2 * i + 1, i]     = -1.0 / di
        A_ub[2 * i + 1, i + 1] =  1.0 / di
        b_ub[2 * i + 1]        =  limit

    A_eq = np.zeros((n, N))
    for i in range(n):
        A_eq[i, i]         = -1.0
        A_eq[i, n + i]     =  1.0
        A_eq[i, 2 * n + i] = -1.0
    b_eq = -ground.copy()

    t_lo = min_track_elev if min_track_elev > -1e8 else None
    bounds = [(t_lo, None)] * n + [(0, None)] * n + [(0, None)] * n

    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub,
                  A_eq=A_eq, b_eq=b_eq,
                  bounds=bounds, method="highs",
                  options={"disp": False, "presolve": True})

    return res.x[:n] if res.success else np.interp(
        chainage, [chainage[0], chainage[-1]], [ground[0], ground[-1]]
    )


# ---------------------------------------------------------------------------
# Coarse-grid spacing
# ---------------------------------------------------------------------------

def _coarse_spacing(params: GeometryParams, total_length: float) -> float:
    K       = max(params.k_crest, params.k_sag)
    L_max   = K * params.max_grade_pct * 2.0
    spacing = L_max * 1.5
    spacing = max(spacing, 1_000.0)
    spacing = min(spacing, total_length / 8.0)
    return max(spacing, 500.0)


# ---------------------------------------------------------------------------
# Parabolic vertical curves
# ---------------------------------------------------------------------------

def _evaluate_with_curves(coarse_ch, track_coarse, fine_ch,
                           k_crest, k_sag, min_dg_pct=0.2):
    n_c     = len(coarse_ch)
    d_c     = np.diff(coarse_ch)
    g_c     = np.diff(track_coarse) / d_c
    track   = np.interp(fine_ch, coarse_ch, track_coarse)
    evc_prev = float(coarse_ch[0]) - 1.0

    for i in range(1, n_c - 1):
        g_before = g_c[i - 1]
        g_after  = g_c[i]
        dg       = g_after - g_before
        dg_pct   = abs(dg) * 100.0
        if dg_pct < min_dg_pct:
            continue
        K      = k_sag if dg > 0 else k_crest
        L      = K * dg_pct
        ch_vip = coarse_ch[i]
        ch_bvc = ch_vip - L / 2.0
        ch_evc = ch_vip + L / 2.0
        if ch_bvc < evc_prev:
            continue
        if i < n_c - 2 and ch_evc > coarse_ch[i + 1]:
            continue
        y_vip = track_coarse[i]
        y_bvc = y_vip - g_before * (L / 2.0)
        mask  = (fine_ch >= ch_bvc) & (fine_ch <= ch_evc)
        if not np.any(mask):
            continue
        x = fine_ch[mask] - ch_bvc
        track[mask] = y_bvc + g_before * x + (dg / (2.0 * L)) * x ** 2
        evc_prev = ch_evc

    return track


# ---------------------------------------------------------------------------
# Volume helpers
# ---------------------------------------------------------------------------

def _cross_section_area(depth, width, batter):
    if depth <= 0:
        return 0.0
    return width * depth + batter * depth ** 2


def _prismatic_volumes(values, chainage, width, batter):
    d = np.diff(chainage)
    return np.array([
        0.5 * (_cross_section_area(values[i],     width, batter) +
               _cross_section_area(values[i + 1], width, batter)) * d[i]
        for i in range(len(d))
    ])


def _prismatic_volumes_geo(values, chainage, width, batter_array):
    """Per-interval prismatic volumes using a per-station batter array."""
    d = np.diff(chainage)
    return np.array([
        0.5 * (_cross_section_area(values[i],     width, batter_array[i]) +
               _cross_section_area(values[i + 1], width, batter_array[i + 1])) * d[i]
        for i in range(len(d))
    ])


# ---------------------------------------------------------------------------
# Structure detection
# ---------------------------------------------------------------------------

def _find_segments(mask, chainage, values):
    segments = []
    in_seg, start_ch, seg_vals = False, 0.0, []
    for i, val in enumerate(mask):
        if val and not in_seg:
            in_seg, start_ch, seg_vals = True, float(chainage[i]), [float(values[i])]
        elif val and in_seg:
            seg_vals.append(float(values[i]))
        elif not val and in_seg:
            in_seg = False
            segments.append((start_ch, float(chainage[i - 1]), max(seg_vals)))
    if in_seg:
        segments.append((start_ch, float(chainage[-1]), max(seg_vals)))
    return segments


# ---------------------------------------------------------------------------
# Grade compensation (ARTC / AS 7634)
# ---------------------------------------------------------------------------

_GRADE_COMP_K = 600.0   # ARTC heavy-freight constant (700 for passenger)
_COMP_R_THRESHOLD = 3000.0  # m — no compensation above this radius

def _compensated_grade_array(chainage: np.ndarray,
                              radii: np.ndarray,
                              max_grade_pct: float) -> np.ndarray:
    """
    Return per-interval grade limit (fraction/m) after applying curve
    compensation:  limit_i = (max_grade - 600/R_i) / 100
    Compensation never reduces the limit below 50% of the design max.
    """
    n = len(chainage)
    r_mid = np.full(n - 1, np.inf)
    for i in range(n - 1):
        r_mid[i] = 0.5 * (radii[i] + radii[i + 1])

    comp = np.where(
        r_mid < _COMP_R_THRESHOLD,
        np.minimum(_GRADE_COMP_K / np.maximum(r_mid, 1.0),
                   max_grade_pct * 0.50),   # cap at 50% reduction
        0.0,
    )
    compensated_pct = np.maximum(max_grade_pct - comp, max_grade_pct * 0.50)
    return compensated_pct / 100.0   # convert to fraction/m


# ---------------------------------------------------------------------------
# Ruling grade
# ---------------------------------------------------------------------------

def _ruling_grade(grade: np.ndarray, chainage: np.ndarray,
                  window_km: float) -> float:
    """
    Worst (highest magnitude) average grade over any window of length
    window_km along the alignment, measured in both directions.
    """
    if window_km <= 0 or len(grade) < 2:
        return float(np.max(np.abs(grade)))
    window_m = window_km * 1000.0
    total    = float(chainage[-1] - chainage[0])
    if total <= window_m:
        # Route shorter than window — use full-route average
        return abs(float((grade[-1] if len(grade) else 0.0)))

    n = len(chainage)
    max_g = 0.0
    j = 0
    for i in range(n):
        while j < n - 1 and (chainage[j] - chainage[i]) < window_m:
            j += 1
        if j == i:
            continue
        dz  = abs(grade[i:j + 1].mean())
        max_g = max(max_g, dz)
    return max_g


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def optimise(profile: np.ndarray, params: GeometryParams,
             radii: Optional[np.ndarray] = None,
             geology=None) -> VerticalAlignment:
    """
    profile : (N, 4) — chainage (m), lat, lng, ground_elev (m).
    radii   : (N,) radius of curvature array from cant.compute_radii().
              If provided, grade compensation is applied on sharp curves.
    """
    chainage = profile[:, 0]
    ground   = profile[:, 3]
    n        = len(ground)
    total    = float(chainage[-1] - chainage[0])

    # ── Step 1: Coarse LP ────────────────────────────────────────────────────
    spacing   = _coarse_spacing(params, total)
    n_coarse  = max(8, int(total / spacing) + 1)
    coarse_ch = np.linspace(float(chainage[0]), float(chainage[-1]), n_coarse)
    ground_c  = np.interp(coarse_ch, chainage, ground)

    # Grade compensation: interpolate radii to coarse grid if available
    grade_comp_applied = False
    max_grade_arr = None
    if radii is not None and len(radii) == n:
        radii_c = np.interp(coarse_ch, chainage, radii)
        grade_arr = _compensated_grade_array(coarse_ch, radii_c, params.max_grade_pct)
        if np.any(grade_arr < params.max_grade_pct / 100.0 * 0.999):
            grade_comp_applied = True
            max_grade_arr = grade_arr
        else:
            max_grade_arr = None

    track_coarse_lp = _lp_grade_line(ground_c, coarse_ch, params.max_grade_pct,
                                     params.min_track_elev_m, max_grade_arr)

    # ── Step 2: Parabolic vertical curves on fine grid ───────────────────────
    track = _evaluate_with_curves(coarse_ch, track_coarse_lp, chainage,
                                   params.k_crest, params.k_sag)

    if params.min_track_elev_m > -1e8:
        track = np.maximum(track, params.min_track_elev_m)

    # ── Step 3: Cut / fill ───────────────────────────────────────────────────
    delta = track - ground
    fill  = np.maximum( delta, 0.0)
    cut   = np.maximum(-delta, 0.0)

    # ── Step 4: Structure detection ──────────────────────────────────────────
    tunnel_mask = cut  > params.cut_trigger_m
    bridge_mask = fill > params.fill_trigger_m

    tunnels = [
        Structure(i + 1, "tunnel", s, e, mx)
        for i, (s, e, mx) in enumerate(_find_segments(tunnel_mask, chainage, cut))
    ]
    bridges = [
        Structure(i + 1, "bridge", s, e, mx)
        for i, (s, e, mx) in enumerate(_find_segments(bridge_mask, chainage, fill))
    ]

    # ── Step 5: Earthwork volumes (exclude structure sections) ───────────────
    ew_cut  = cut.copy();  ew_cut[tunnel_mask]  = 0.0
    ew_fill = fill.copy(); ew_fill[bridge_mask] = 0.0

    total_cut  = float(np.sum(_prismatic_volumes(ew_cut,  chainage,
                                                  params.formation_width_m,
                                                  params.batter_cut)))
    total_fill = float(np.sum(_prismatic_volumes(ew_fill, chainage,
                                                  params.formation_width_m,
                                                  params.batter_fill)))

    # Geology-adjusted volumes (per-station batter arrays)
    geo_cut, geo_fill = 0.0, 0.0
    geo_applied = False
    if (geology is not None
            and hasattr(geology, "batter_cut_array")
            and len(geology.batter_cut_array) == n):
        geo_cut = float(np.sum(_prismatic_volumes_geo(
            ew_cut,  chainage, params.formation_width_m,
            geology.batter_cut_array)))
        geo_fill = float(np.sum(_prismatic_volumes_geo(
            ew_fill, chainage, params.formation_width_m,
            geology.batter_fill_array)))
        geo_applied = True

    # ── Step 6: Grade array ──────────────────────────────────────────────────
    grade = np.zeros(n)
    grade[:-1] = np.diff(track) / np.diff(chainage) * 100.0
    grade[-1]  = grade[-2]

    # ── Step 7: Ruling grade ─────────────────────────────────────────────────
    ruling = _ruling_grade(grade, chainage, params.ruling_grade_length_km)

    # ── Step 8: Constraint violations ────────────────────────────────────────
    violations: List[Tuple] = []
    max_g = float(np.max(np.abs(grade)))
    if max_g > params.max_grade_pct * 1.02:
        idx = int(np.argmax(np.abs(grade)))
        violations.append((chainage[idx],
                           f"Grade {max_g:.2f}% exceeds limit "
                           f"{params.max_grade_pct:.2f}%"))

    return VerticalAlignment(
        chainage=chainage, ground=ground, track=track,
        cut=cut, fill=fill, grade=grade,
        total_cut_m3=total_cut, total_fill_m3=total_fill,
        max_grade_pct=max_g, violations=violations,
        tunnels=tunnels, bridges=bridges,
        min_track_elev_m=params.min_track_elev_m,
        ruling_grade_pct=ruling,
        grade_compensation_applied=grade_comp_applied,
        geology_adjusted_cut_m3=geo_cut,
        geology_adjusted_fill_m3=geo_fill,
        geology_applied=geo_applied,
    )
