"""
Approximate construction cost estimator for railway alignments.

All rates are in 2024 AUD and are based on publicly available Australian
infrastructure benchmarks (BITRE, Infrastructure Australia, QLD/NSW project
reports, and Aurecon/AECOM reference schedules).

Every rate is configurable via CostBands — the defaults are reasonable
starting points for a pre-feasibility study (Class 5, ±50%).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Tuple
import numpy as np


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class CostBands:
    # ── Earthworks: Cut rate ($/m³) by geology ──────────────────────────────
    # Includes excavation, hauling, tipping or stockpile.
    cut_A: float = 90.0    # Hard rock  — drill & blast + truck + tip
    cut_B: float = 55.0    # Medium rock — rip or light blast + excavate
    cut_C: float = 32.0    # Weak rock  — rip or direct dig
    cut_D: float = 20.0    # Soft ground — dozer/scraper
    cut_unknown: float = 40.0

    # ── Earthworks: Fill rate ($/m³) by geology ──────────────────────────────
    # Includes place, spread and compact in 300 mm layers.
    fill_A: float = 40.0   # Quarried rock fill — harder to compact
    fill_B: float = 30.0   # Medium rock fill
    fill_C: float = 25.0   # Weak rock / imported select fill
    fill_D: float = 20.0   # Soft compacted fill
    fill_unknown: float = 28.0

    # ── Cut depth multipliers (applied on top of base cut rate) ─────────────
    # Accounts for extra benching, drainage, slope monitoring.
    cut_band1_m: float = 5.0     # shallow → medium boundary (m depth)
    cut_band2_m: float = 15.0    # medium  → deep   boundary
    cut_mult_medium: float = 1.30   # 5–15 m depth
    cut_mult_deep:   float = 1.60   # > 15 m depth

    # ── Fill height multipliers ──────────────────────────────────────────────
    # Accounts for reinforced fill, geotextile, toe protection.
    fill_band1_m: float = 3.0
    fill_band2_m: float = 8.0
    fill_mult_medium: float = 1.20  # 3–8 m
    fill_mult_high:   float = 1.40  # > 8 m

    # ── Bridge rate ($/m of bridge length) by average height above ground ───
    bridge_band1_m: float = 5.0
    bridge_band2_m: float = 15.0
    bridge_rate_low:    float = 30_000.0   # < 5 m — simple deck on spread footings
    bridge_rate_medium: float = 65_000.0   # 5–15 m — piers + post-tensioned deck
    bridge_rate_high:   float = 120_000.0  # > 15 m — tall piers / viaduct

    # ── Tunnel rate ($/m) by geology ────────────────────────────────────────
    tunnel_A: float = 45_000.0   # Hard rock — drill & blast, rock bolts + shotcrete
    tunnel_B: float = 75_000.0   # Medium rock — controlled blast + support
    tunnel_C: float = 100_000.0  # Weak rock  — NATM / heavy shotcrete lining
    tunnel_D: float = 130_000.0  # Soft ground — TBM or NATM + ground treatment
    tunnel_unknown: float = 90_000.0

    # ── Track supply & lay ($/m of alignment) — single track basis ──────────
    track_rail:       float = 150.0   # 60 kg/m rail supply & lay
    track_sleeper:    float = 280.0   # Concrete sleepers @ 600 mm centres
    track_ballast:    float = 140.0   # 300 mm ballast, ~4.5 m wide
    track_capping:    float = 75.0    # 150 mm capping / subballast layer
    track_fastenings: float = 80.0    # Fastenings, pads, anchors
    track_drainage:   float = 60.0    # Lineside open drains
    track_formation:  float = 115.0   # Final formation trim & compact
    double_track_factor: float = 1.8  # Double ≈ single × factor (shared corridor)

    # ── Rail systems (signalling, comms, ETCS, power) ───────────────────────
    signalling_per_m: float = 250.0   # $/m — ETCS level 2 / ATP
    comms_per_m: float = 80.0         # $/m — fibre, radio, lineside
    power_per_m: float = 120.0        # $/m — traction power (electrification) or gensets

    # ── Contingency ──────────────────────────────────────────────────────────
    contingency_pct: float = 20.0  # %

    # Formation width — used for cross-section volume estimate (m)
    formation_width_m: float = 5.5   # standard gauge single track

    @property
    def track_single_per_m(self) -> float:
        return (self.track_rail + self.track_sleeper + self.track_ballast
                + self.track_capping + self.track_fastenings
                + self.track_drainage + self.track_formation)

    @property
    def track_double_per_m(self) -> float:
        return self.track_single_per_m * self.double_track_factor


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CostLine:
    label: str
    quantity: float
    unit: str
    rate: float      # $/unit
    subtotal: float  # quantity × rate


@dataclass
class CostResult:
    lines_cut:     List[CostLine]
    lines_fill:    List[CostLine]
    lines_bridges: List[CostLine]
    lines_tunnels: List[CostLine]
    lines_track:   List[CostLine]
    lines_systems: List[CostLine]
    contingency_pct: float
    route_length_km: float
    double_track: bool

    @property
    def subtotal_cut(self):        return sum(l.subtotal for l in self.lines_cut)
    @property
    def subtotal_fill(self):       return sum(l.subtotal for l in self.lines_fill)
    @property
    def subtotal_earthworks(self): return self.subtotal_cut + self.subtotal_fill
    @property
    def subtotal_bridges(self):    return sum(l.subtotal for l in self.lines_bridges)
    @property
    def subtotal_tunnels(self):    return sum(l.subtotal for l in self.lines_tunnels)
    @property
    def subtotal_track(self):      return sum(l.subtotal for l in self.lines_track)
    @property
    def subtotal_systems(self):    return sum(l.subtotal for l in self.lines_systems)

    @property
    def subtotal_base(self):
        return (self.subtotal_earthworks + self.subtotal_bridges
                + self.subtotal_tunnels + self.subtotal_track
                + self.subtotal_systems)

    @property
    def contingency_amount(self):
        return self.subtotal_base * self.contingency_pct / 100

    @property
    def total(self):
        return self.subtotal_base + self.contingency_amount


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_GEO_LABELS: Dict[str, str] = {
    "A": "Hard Rock", "B": "Med Rock",
    "C": "Weak Rock", "D": "Soft Gnd", "?": "Unknown",
}
_CUT_BAND_LBL  = {"shallow": "<5 m",  "medium": "5–15 m", "deep": ">15 m"}
_FILL_BAND_LBL = {"low":    "<3 m",   "medium": "3–8 m",  "high": ">8 m"}


def _geo_class_at(chainage_val: float, geology) -> str:
    if geology is None:
        return "?"
    for seg in geology.segments:
        if seg.start_ch <= chainage_val <= seg.end_ch:
            return seg.eng_class
    return "?"


def _cut_rate(geo: str, cfg: CostBands) -> float:
    return {"A": cfg.cut_A, "B": cfg.cut_B,
            "C": cfg.cut_C, "D": cfg.cut_D}.get(geo, cfg.cut_unknown)


def _fill_rate(geo: str, cfg: CostBands) -> float:
    return {"A": cfg.fill_A, "B": cfg.fill_B,
            "C": cfg.fill_C, "D": cfg.fill_D}.get(geo, cfg.fill_unknown)


def _tunnel_rate(geo: str, cfg: CostBands) -> float:
    return {"A": cfg.tunnel_A, "B": cfg.tunnel_B,
            "C": cfg.tunnel_C, "D": cfg.tunnel_D}.get(geo, cfg.tunnel_unknown)


# ---------------------------------------------------------------------------
# Main estimation function
# ---------------------------------------------------------------------------

def estimate_costs(alignment, geology, cfg: CostBands,
                   double_track: bool = False) -> CostResult:
    """
    Compute approximate construction costs.

    alignment  : VerticalAlignment (from optimizer.py)
    geology    : GeologyResult or None
    cfg        : CostBands (all configurable rates)
    double_track: if True, track costs use double_track_factor
    """
    chainage = alignment.chainage
    ground   = alignment.ground
    track    = alignment.track
    n        = len(chainage)
    route_km = float(chainage[-1] - chainage[0]) / 1000.0

    # ── Mask tunnel and bridge zones (excluded from earthwork volumes) ────────
    struct_mask = np.zeros(n, dtype=bool)
    for st in list(alignment.tunnels) + list(alignment.bridges):
        struct_mask |= (chainage >= st.start_ch) & (chainage <= st.end_ch)

    # ── Per-station cut depth / fill height ───────────────────────────────────
    diff         = track - ground
    cut_depth    = np.where(~struct_mask, np.maximum(0.0, -diff), 0.0)
    fill_height  = np.where(~struct_mask, np.maximum(0.0,  diff), 0.0)

    # ── Per-station batter ratios (geology-aware) ─────────────────────────────
    if geology is not None:
        batter_cut  = geology.batter_cut_array
        batter_fill = geology.batter_fill_array
    else:
        batter_cut  = np.full(n, 1.5)
        batter_fill = np.full(n, 2.0)

    w = cfg.formation_width_m
    cut_area  = cut_depth  * w + cut_depth**2  * batter_cut
    fill_area = fill_height * w + fill_height**2 * batter_fill

    # ── Interval volumes (trapezoidal rule) ───────────────────────────────────
    dx       = np.diff(chainage)
    cut_vol  = 0.5 * (cut_area[:-1]  + cut_area[1:])  * dx
    fill_vol = 0.5 * (fill_area[:-1] + fill_area[1:]) * dx
    ch_mid   = 0.5 * (chainage[:-1]  + chainage[1:])
    cut_mid  = 0.5 * (cut_depth[:-1]  + cut_depth[1:])
    fill_mid = 0.5 * (fill_height[:-1] + fill_height[1:])

    # ── Accumulate cost by (geology_class, height_band) ───────────────────────
    cut_acc:  Dict[Tuple[str, str], List[float]] = {}
    fill_acc: Dict[Tuple[str, str], List[float]] = {}

    for i in range(len(dx)):
        geo = _geo_class_at(float(ch_mid[i]), geology)

        if cut_vol[i] > 0:
            d = float(cut_mid[i])
            if d <= cfg.cut_band1_m:
                band, mult = "shallow", 1.0
            elif d <= cfg.cut_band2_m:
                band, mult = "medium", cfg.cut_mult_medium
            else:
                band, mult = "deep", cfg.cut_mult_deep
            rate = _cut_rate(geo, cfg) * mult
            k = (geo, band)
            row = cut_acc.setdefault(k, [0.0, 0.0])
            row[0] += cut_vol[i]
            row[1] += cut_vol[i] * rate

        if fill_vol[i] > 0:
            h = float(fill_mid[i])
            if h <= cfg.fill_band1_m:
                band, mult = "low", 1.0
            elif h <= cfg.fill_band2_m:
                band, mult = "medium", cfg.fill_mult_medium
            else:
                band, mult = "high", cfg.fill_mult_high
            rate = _fill_rate(geo, cfg) * mult
            k = (geo, band)
            row = fill_acc.setdefault(k, [0.0, 0.0])
            row[0] += fill_vol[i]
            row[1] += fill_vol[i] * rate

    lines_cut = [
        CostLine(
            label=f"Cut  {_GEO_LABELS.get(g,'?')} {_CUT_BAND_LBL[b]}",
            quantity=v, unit="m³",
            rate=c / v if v else 0.0,
            subtotal=c,
        )
        for (g, b), (v, c) in sorted(cut_acc.items()) if v > 1
    ]

    lines_fill = [
        CostLine(
            label=f"Fill {_GEO_LABELS.get(g,'?')} {_FILL_BAND_LBL[b]}",
            quantity=v, unit="m³",
            rate=c / v if v else 0.0,
            subtotal=c,
        )
        for (g, b), (v, c) in sorted(fill_acc.items()) if v > 1
    ]

    # ── Bridges ───────────────────────────────────────────────────────────────
    lines_bridges = []
    for bridge in alignment.bridges:
        s, e = bridge.start_ch, bridge.end_ch
        mask_b = (chainage >= s) & (chainage <= e)
        h = float(np.mean(np.maximum(0.0, track[mask_b] - ground[mask_b]))) \
            if mask_b.any() else 5.0
        if h < cfg.bridge_band1_m:
            rate  = cfg.bridge_rate_low
            hlbl  = f"low  ht (avg {h:.0f} m)"
        elif h < cfg.bridge_band2_m:
            rate  = cfg.bridge_rate_medium
            hlbl  = f"med  ht (avg {h:.0f} m)"
        else:
            rate  = cfg.bridge_rate_high
            hlbl  = f"high ht (avg {h:.0f} m)"
        lines_bridges.append(CostLine(
            label=f"Bridge B{bridge.index} — {hlbl}",
            quantity=bridge.length_m, unit="m",
            rate=rate, subtotal=bridge.length_m * rate,
        ))

    # ── Tunnels ───────────────────────────────────────────────────────────────
    lines_tunnels = []
    for tunnel in alignment.tunnels:
        geo  = _geo_class_at(0.5 * (tunnel.start_ch + tunnel.end_ch), geology)
        rate = _tunnel_rate(geo, cfg)
        lines_tunnels.append(CostLine(
            label=f"Tunnel T{tunnel.index} — {_GEO_LABELS.get(geo,'?')}",
            quantity=tunnel.length_m, unit="m",
            rate=rate, subtotal=tunnel.length_m * rate,
        ))

    # ── Track ─────────────────────────────────────────────────────────────────
    length_m = float(chainage[-1] - chainage[0])
    factor   = cfg.double_track_factor if double_track else 1.0
    comps = [
        ("Rail 60 kg/m, supply & lay",   cfg.track_rail),
        ("Concrete sleepers @ 600 mm",   cfg.track_sleeper),
        ("Ballast 300 mm depth",          cfg.track_ballast),
        ("Capping / subballast layer",    cfg.track_capping),
        ("Fastenings, pads & anchors",    cfg.track_fastenings),
        ("Lineside drainage",             cfg.track_drainage),
        ("Formation preparation",         cfg.track_formation),
    ]
    lines_track = [
        CostLine(label=lbl, quantity=length_m, unit="m",
                 rate=r * factor, subtotal=length_m * r * factor)
        for lbl, r in comps
    ]

    # ── Rail systems ──────────────────────────────────────────────────────────
    sys_comps = [
        ("Signalling (ETCS/ATP)",        cfg.signalling_per_m),
        ("Communications (fibre/radio)",  cfg.comms_per_m),
        ("Power / electrification",       cfg.power_per_m),
    ]
    lines_systems = [
        CostLine(label=lbl, quantity=length_m, unit="m",
                 rate=r, subtotal=length_m * r)
        for lbl, r in sys_comps
    ]

    return CostResult(
        lines_cut=lines_cut,
        lines_fill=lines_fill,
        lines_bridges=lines_bridges,
        lines_tunnels=lines_tunnels,
        lines_track=lines_track,
        lines_systems=lines_systems,
        contingency_pct=cfg.contingency_pct,
        route_length_km=route_km,
        double_track=double_track,
    )
