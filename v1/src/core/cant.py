"""
Cant (superelevation), speed, transition, and track-twist analysis.

Pipeline (called from the analysis worker thread):
  1. compute_radii(profile)         → radii array at every station
  2. analyse_cant(chainage, radii, params) → CantAnalysis

Cant factor derivation
----------------------
  C_eq (mm) = G_mm × V_kph² / (3.6² × 9.81 × R_m)
             = G_mm × V_kph² / 127.06 / R_m
  For standard gauge (1435 mm): factor ≈ 11.30
  The commonly quoted "11.8" includes a small empirical correction
  for track spread; we use the exact formula with gauge as input.

Max permissible speed (solve for V):
  V_max = sqrt( (C_actual + D_max) × 127.06 × R / G_mm )
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List

_R_EARTH = 6_371_000.0          # m
_CANT_FACTOR_DENOM = 127.06     # 3.6² × 9.81
_STRAIGHT_R = 10_000.0          # m — radii above this treated as tangent


# ---------------------------------------------------------------------------
# Radius computation (standalone so it can run in the worker thread)
# ---------------------------------------------------------------------------

def compute_radii(profile: np.ndarray, stencil_m: float = 100.0) -> np.ndarray:
    """
    Radius of curvature (m) at each station from a (N,4) profile array
    (chainage, lat, lng, elev).  Capped at 50 km (effectively straight).
    Uses a ±stencil_m three-point circumradius.
    """
    lats = profile[:, 1]
    lons = profile[:, 2]
    ch   = profile[:, 0]
    n    = len(lats)

    lat0_r = np.radians(np.mean(lats))
    x = (lons - np.mean(lons)) * np.cos(lat0_r) * (np.pi / 180.0) * _R_EARTH
    y = (lats - np.mean(lats)) * (np.pi / 180.0) * _R_EARTH

    ch_step = float(np.median(np.diff(ch))) if n > 1 else 10.0
    k = max(1, int(round(stencil_m / ch_step)))

    radii = np.full(n, np.inf)
    for i in range(k, n - k):
        radii[i] = _circumradius(x[i - k], y[i - k],
                                  x[i],     y[i],
                                  x[i + k], y[i + k])
    radii[:k]     = radii[k]
    radii[n - k:] = radii[max(0, n - k - 1)]
    return np.minimum(radii, 50_000.0)


def _circumradius(x1, y1, x2, y2, x3, y3) -> float:
    ax, ay = x2 - x1, y2 - y1
    bx, by = x3 - x1, y3 - y1
    area2  = abs(ax * by - bx * ay)
    if area2 < 1e-6:
        return np.inf
    a = np.hypot(x3 - x2, y3 - y2)
    b = np.hypot(x3 - x1, y3 - y1)
    c = np.hypot(x2 - x1, y2 - y1)
    return (a * b * c) / (2.0 * area2)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CurveSection:
    index: int
    start_ch: float
    end_ch: float
    radius_m: float
    equilibrium_cant_mm: float
    actual_cant_mm: float
    cant_deficiency_mm: float
    max_speed_kph: float
    required_transition_m: float  # L_trans = C_actual / cant_gradient_max
    arc_length_m: float
    transition_fits: bool         # arc ≥ 2 × L_trans

    @property
    def length_m(self) -> float:
        return self.end_ch - self.start_ch


@dataclass
class ReverseCurveViolation:
    """Tangent between consecutive curves is shorter than required."""
    index: int
    start_ch: float   # end of curve i
    end_ch: float     # start of curve i+1
    tangent_length_m: float
    required_m: float


@dataclass
class CoincidentCurveViolation:
    """A vertical curve VIP falls inside a horizontal curve section."""
    chainage_m: float
    h_radius_m: float
    description: str


@dataclass
class CantAnalysis:
    chainage: np.ndarray
    radii: np.ndarray
    equilibrium_cant: np.ndarray    # mm per station
    actual_cant: np.ndarray         # mm per station (ramped through transitions)
    cant_deficiency: np.ndarray     # mm per station
    max_speed: np.ndarray           # km/h per station
    rate_of_change_cant: np.ndarray # mm/m — cant gradient along alignment
    twist_3m: np.ndarray            # mm per 3 m base
    curves: List[CurveSection]      = field(default_factory=list)
    reverse_violations: List[ReverseCurveViolation] = field(default_factory=list)
    design_speed_kph: float         = 0.0
    min_speed_kph: float            = 0.0
    max_twist_limit_mm: float       = 7.0   # limit used for violation counting
    max_cant_limit_mm: float        = 100.0 # max cant param (for chart line)
    speed_restricted_stations: int  = 0
    twist_violation_stations: int   = 0
    transition_violation_count: int = 0
    reverse_violation_count: int    = 0


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def analyse_cant(chainage: np.ndarray, radii: np.ndarray, params) -> CantAnalysis:
    """
    params must expose:
        design_speed_kph, gauge_mm, max_cant_mm, max_cant_deficiency_mm,
        cant_gradient_max_mm_per_m, max_twist_mm_per_3m
    """
    V          = float(params.design_speed_kph)
    G          = float(params.gauge_mm)
    C_max      = float(params.max_cant_mm)
    D_max      = float(params.max_cant_deficiency_mm)
    grad_max   = float(params.cant_gradient_max_mm_per_m)
    twist_lim  = float(params.max_twist_mm_per_3m)

    cant_factor = G / _CANT_FACTOR_DENOM   # C_eq = cant_factor × V² / R

    n = len(chainage)

    # ── Per-station equilibrium cant ─────────────────────────────────────────
    with np.errstate(divide="ignore", invalid="ignore"):
        eq_cant = np.where(
            radii < _STRAIGHT_R,
            cant_factor * V * V / np.maximum(radii, 1.0),
            0.0,
        )
    eq_cant = np.clip(eq_cant, 0.0, 500.0)

    act_cant_simple = np.minimum(eq_cant, C_max)
    deficiency      = np.clip(eq_cant - act_cant_simple, 0.0, None)

    # ── Per-station max permissible speed ────────────────────────────────────
    with np.errstate(divide="ignore", invalid="ignore"):
        max_speed = np.where(
            radii < _STRAIGHT_R,
            np.sqrt(np.maximum(
                (act_cant_simple + D_max) * _CANT_FACTOR_DENOM * radii / G,
                0.0,
            )),
            V,
        )
    max_speed = np.minimum(max_speed, V)

    # ── Identify curve sections ───────────────────────────────────────────────
    curves: List[CurveSection] = []
    curve_mask = radii < _STRAIGHT_R
    in_curve, seg_start = False, 0

    for i in range(n):
        if curve_mask[i] and not in_curve:
            in_curve, seg_start = True, i
        elif not curve_mask[i] and in_curve:
            in_curve = False
            curves.append(_make_curve(seg_start, i - 1, chainage, radii,
                                       cant_factor, V, G, C_max, D_max,
                                       grad_max, len(curves)))
    if in_curve:
        curves.append(_make_curve(seg_start, n - 1, chainage, radii,
                                   cant_factor, V, G, C_max, D_max,
                                   grad_max, len(curves)))

    # ── Build smooth cant profile (ramp through transitions) ─────────────────
    act_cant = _build_cant_profile(chainage, curves)

    # ── Rate of change of cant (mm/m) ────────────────────────────────────────
    d_ch = np.diff(chainage)
    d_ch = np.where(d_ch < 1e-3, 1e-3, d_ch)
    roc  = np.zeros(n)
    roc[:-1] = np.abs(np.diff(act_cant)) / d_ch
    roc[-1]  = roc[-2]

    # ── Track twist (mm per 3 m base) ────────────────────────────────────────
    twist = roc * 3.0

    # ── Reverse curve checks ─────────────────────────────────────────────────
    reverse_violations: List[ReverseCurveViolation] = []
    for i in range(len(curves) - 1):
        c1, c2   = curves[i], curves[i + 1]
        tan_len  = c2.start_ch - c1.end_ch
        required = c1.required_transition_m + c2.required_transition_m
        if tan_len < required:
            reverse_violations.append(ReverseCurveViolation(
                index=len(reverse_violations) + 1,
                start_ch=c1.end_ch,
                end_ch=c2.start_ch,
                tangent_length_m=max(tan_len, 0.0),
                required_m=required,
            ))

    speed_rest = int(np.sum(max_speed < V * 0.99))
    twist_viol = int(np.sum(twist > twist_lim))
    trans_viol = sum(1 for c in curves if not c.transition_fits)
    min_spd    = float(np.min(max_speed)) if n else V

    return CantAnalysis(
        chainage=chainage,
        radii=radii,
        equilibrium_cant=eq_cant,
        actual_cant=act_cant,
        cant_deficiency=deficiency,
        max_speed=max_speed,
        rate_of_change_cant=roc,
        twist_3m=twist,
        curves=curves,
        reverse_violations=reverse_violations,
        design_speed_kph=V,
        min_speed_kph=min_spd,
        max_twist_limit_mm=twist_lim,
        max_cant_limit_mm=C_max,
        speed_restricted_stations=speed_rest,
        twist_violation_stations=twist_viol,
        transition_violation_count=trans_viol,
        reverse_violation_count=len(reverse_violations),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_curve(start_i: int, end_i: int,
                chainage, radii,
                cant_factor, V, G, C_max, D_max, grad_max,
                existing_count: int) -> CurveSection:
    r    = float(np.median(radii[start_i:end_i + 1]))
    ceq  = cant_factor * V * V / max(r, 1.0)
    cact = min(ceq, C_max)
    cdef = max(ceq - cact, 0.0)
    vmax = min(V, float(np.sqrt(max((cact + D_max) * _CANT_FACTOR_DENOM * r / G, 0.0))))
    L_t  = cact / max(grad_max, 0.01)
    arc  = float(chainage[end_i] - chainage[start_i])
    return CurveSection(
        index=existing_count + 1,
        start_ch=float(chainage[start_i]),
        end_ch=float(chainage[end_i]),
        radius_m=r,
        equilibrium_cant_mm=ceq,
        actual_cant_mm=cact,
        cant_deficiency_mm=cdef,
        max_speed_kph=vmax,
        required_transition_m=L_t,
        arc_length_m=arc,
        transition_fits=(arc >= 2.0 * L_t),
    )


def _build_cant_profile(chainage: np.ndarray,
                         curves: List[CurveSection]) -> np.ndarray:
    """
    Build a station-level cant array that ramps linearly through entry and
    exit transitions and holds the full value through the circular body.
    Where the arc is too short for both transitions, the cant is ramped to
    the mid-point and immediately ramped back (no flat top).
    """
    cant = np.zeros(len(chainage))

    for curve in curves:
        L_t   = curve.required_transition_m
        C     = curve.actual_cant_mm
        s, e  = curve.start_ch, curve.end_ch
        mid   = (s + e) / 2.0
        e_end = min(s + L_t, mid)   # end of entry ramp
        x_start = max(e - L_t, mid) # start of exit ramp

        m_entry = (chainage >= s)     & (chainage <= e_end)
        m_body  = (chainage > e_end)  & (chainage < x_start)
        m_exit  = (chainage >= x_start) & (chainage <= e)

        if np.any(m_entry) and e_end > s:
            t = (chainage[m_entry] - s) / (e_end - s)
            cant[m_entry] = np.maximum(cant[m_entry], C * t)

        if np.any(m_body):
            cant[m_body] = np.maximum(cant[m_body], C)

        if np.any(m_exit) and e > x_start:
            t = (e - chainage[m_exit]) / (e - x_start)
            cant[m_exit] = np.maximum(cant[m_exit], C * t)

    return cant


def detect_coincident_curves(grade: np.ndarray,
                              chainage: np.ndarray,
                              radii: np.ndarray,
                              min_radius_m: float,
                              min_dg_pct: float = 0.3) -> List[CoincidentCurveViolation]:
    """
    Flag stations where a significant grade change (vertical curve zone)
    coincides with a horizontal curve (radius < min_radius_m).
    """
    violations: List[CoincidentCurveViolation] = []
    n = len(grade)

    # Rate of grade change — high values indicate proximity to a VIP
    d_ch = np.diff(chainage)
    d_ch = np.where(d_ch < 1e-3, 1e-3, d_ch)
    dg   = np.abs(np.diff(grade)) / d_ch * 100.0   # %/m
    dg   = np.append(dg, dg[-1] if len(dg) else 0.0)

    # Threshold: top 5% of grade-change rate OR > min_dg_pct %/100m
    threshold = max(float(np.percentile(dg, 95)), min_dg_pct / 100.0)
    vc_zone   = dg > threshold
    h_curve   = radii < min_radius_m

    combined = vc_zone & h_curve
    # Collapse consecutive flagged stations into single events
    in_viol, last_ch = False, 0.0
    for i in range(n):
        if combined[i] and not in_viol:
            in_viol = True
            last_ch = chainage[i]
        elif not combined[i] and in_viol:
            in_viol = False
            violations.append(CoincidentCurveViolation(
                chainage_m=last_ch,
                h_radius_m=float(np.mean(radii[max(0, i - 5):i])),
                description=(
                    f"Vertical curve zone coincides with horizontal curve "
                    f"(R ≈ {float(np.mean(radii[max(0,i-5):i])):.0f} m)"
                ),
            ))
    return violations
