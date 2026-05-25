"""
Horizontal alignment chart.

Left panel  — Plan view: route coloured by radius compliance.
              Reverse-curve violations shown as orange markers.
Right panel — Radius profile: curvature radius vs chainage.

Accepts pre-computed radii from cant.compute_radii() so the worker thread
does not recompute them.  Falls back to internal computation if not supplied.
"""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
import matplotlib.patches as mpatches

_R_EARTH = 6_371_000.0

_COL = {
    "ok":       "#38bdf8",
    "bad":      "#ef4444",
    "reverse":  "#f97316",   # reverse-curve tangent violation
    "start":    "#22c55e",
    "end":      "#f97316",
    "min":      "#f59e0b",
}


# ---------------------------------------------------------------------------
# Geometry (kept here for fall-back when radii are not pre-supplied)
# ---------------------------------------------------------------------------

def _to_local_xy(lats, lons):
    lat0_r = np.radians(np.mean(lats))
    x = (lons - np.mean(lons)) * np.cos(lat0_r) * (np.pi / 180.0) * _R_EARTH
    y = (lats - np.mean(lats)) * (np.pi / 180.0) * _R_EARTH
    return x, y


def _circumradius(x1, y1, x2, y2, x3, y3):
    ax, ay = x2 - x1, y2 - y1
    bx, by = x3 - x1, y3 - y1
    area2  = abs(ax * by - bx * ay)
    if area2 < 1e-6:
        return np.inf
    a = np.hypot(x3 - x2, y3 - y2)
    b = np.hypot(x3 - x1, y3 - y1)
    c = np.hypot(x2 - x1, y2 - y1)
    return (a * b * c) / (2.0 * area2)


def _radius_profile(x, y, ch_spacing_m=10.0):
    n = len(x)
    k = max(1, int(round(100.0 / ch_spacing_m)))
    radii = np.full(n, np.inf)
    for i in range(k, n - k):
        radii[i] = _circumradius(x[i - k], y[i - k],
                                  x[i],     y[i],
                                  x[i + k], y[i + k])
    radii[:k]    = radii[k]
    radii[n - k:] = radii[max(0, n - k - 1)]
    return np.minimum(radii, 50_000.0)


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class HorizontalWidget(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 3.8), facecolor="#0f172a")
        super().__init__(self.fig)
        self.setParent(parent)

        gs = self.fig.add_gridspec(1, 2, width_ratios=[2, 1], wspace=0.32)
        self._ax_plan   = self.fig.add_subplot(gs[0])
        self._ax_radius = self.fig.add_subplot(gs[1])

        self._style_axes()
        self._draw_empty()

    def _style_axes(self):
        for ax in (self._ax_plan, self._ax_radius):
            ax.set_facecolor("#0f172a")
            ax.tick_params(colors="#94a3b8", labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor("#334155")
        self._ax_plan.set_xlabel("Easting (km)",    color="#94a3b8", fontsize=9)
        self._ax_plan.set_ylabel("Northing (km)",   color="#94a3b8", fontsize=9)
        self._ax_radius.set_xlabel("Chainage (km)", color="#94a3b8", fontsize=9)
        self._ax_radius.set_ylabel("Radius (m)",    color="#94a3b8", fontsize=9)
        self.fig.tight_layout(pad=1.4)

    def _draw_empty(self):
        self._ax_plan.clear()
        self._ax_radius.clear()
        self._style_axes()
        self._ax_plan.text(
            0.5, 0.5,
            "Analyse a route to see the horizontal alignment.",
            transform=self._ax_plan.transAxes,
            ha="center", va="center", color="#475569", fontsize=11,
        )
        self.draw()

    # ------------------------------------------------------------------ update

    def update_alignment(self, profile: np.ndarray, min_radius_m: float,
                         radii: np.ndarray = None,
                         cant_analysis=None):
        """
        profile       : (N,4) chainage, lat, lng, elev
        min_radius_m  : design minimum radius
        radii         : pre-computed radii array (optional — computed here if None)
        cant_analysis : CantAnalysis (optional — used for reverse-curve markers)
        """
        self._ax_plan.clear()
        self._ax_radius.clear()
        self._style_axes()

        ch   = profile[:, 0]
        lats = profile[:, 1]
        lons = profile[:, 2]
        ch_km = ch / 1000.0

        x, y   = _to_local_xy(lats, lons)
        x_km   = x / 1000.0
        y_km   = y / 1000.0

        if radii is None:
            ch_step = float(np.median(np.diff(ch))) if len(ch) > 1 else 10.0
            radii   = _radius_profile(x, y, ch_step)

        # ── Plan view ────────────────────────────────────────────────────────
        pts  = np.column_stack([x_km, y_km]).reshape(-1, 1, 2)
        segs = np.concatenate([pts[:-1], pts[1:]], axis=1)
        ok   = radii[:-1] >= min_radius_m

        for mask, color in ((ok, _COL["ok"]), (~ok, _COL["bad"])):
            if mask.any():
                lc = LineCollection(segs[mask], color=color,
                                    linewidth=2.2, alpha=0.9, zorder=3)
                self._ax_plan.add_collection(lc)

        # Reverse-curve violation markers
        if cant_analysis is not None:
            for rv in cant_analysis.reverse_violations:
                mid_ch = (rv.start_ch + rv.end_ch) / 2.0
                idx    = int(np.argmin(np.abs(ch - mid_ch)))
                self._ax_plan.scatter(x_km[idx], y_km[idx],
                                      color=_COL["reverse"], s=80, marker="^",
                                      zorder=6,
                                      label="_reverse")
            # Transition violations
            for curve in cant_analysis.curves:
                if not curve.transition_fits:
                    mid_ch = (curve.start_ch + curve.end_ch) / 2.0
                    idx    = int(np.argmin(np.abs(ch - mid_ch)))
                    self._ax_plan.scatter(x_km[idx], y_km[idx],
                                          color="#a855f7", s=60, marker="D",
                                          zorder=6, label="_trans")

        # Start / end markers
        self._ax_plan.scatter(x_km[0],  y_km[0],  color=_COL["start"],
                              s=70, zorder=5, marker="o")
        self._ax_plan.scatter(x_km[-1], y_km[-1], color=_COL["end"],
                              s=70, zorder=5, marker="s")

        span = max(x_km.max() - x_km.min(), y_km.max() - y_km.min(), 0.1)
        pad  = span * 0.06 + 0.3
        self._ax_plan.set_xlim(x_km.min() - pad, x_km.max() + pad)
        self._ax_plan.set_ylim(y_km.min() - pad, y_km.max() + pad)
        self._ax_plan.set_aspect("equal", adjustable="box")
        self._ax_plan.set_xlabel("Easting (km)",  color="#94a3b8", fontsize=9)
        self._ax_plan.set_ylabel("Northing (km)", color="#94a3b8", fontsize=9)

        n_viol = int(np.sum(radii < min_radius_m))
        legend_handles = [
            mpatches.Patch(color=_COL["ok"],  label=f"R ≥ {min_radius_m:.0f} m"),
            mpatches.Patch(color=_COL["bad"], label=f"R < {min_radius_m:.0f} m"),
            mpatches.Patch(color=_COL["start"], label="Start"),
            mpatches.Patch(color=_COL["end"],   label="End"),
        ]
        if cant_analysis and cant_analysis.reverse_violation_count:
            legend_handles.append(
                mpatches.Patch(color=_COL["reverse"],
                               label=f"Rev. curve: {cant_analysis.reverse_violation_count}")
            )
        if cant_analysis and cant_analysis.transition_violation_count:
            legend_handles.append(
                mpatches.Patch(color="#a855f7",
                               label=f"Trans. short: {cant_analysis.transition_violation_count}")
            )
        self._ax_plan.legend(
            handles=legend_handles, loc="best", fontsize=8,
            facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0",
            framealpha=0.9,
        )

        # ── Radius profile ────────────────────────────────────────────────────
        disp = np.minimum(radii, 10_000.0)
        self._ax_radius.plot(ch_km, disp, color="#64748b",
                             linewidth=0.9, zorder=2)
        self._ax_radius.fill_between(ch_km, disp, 0,
                                     where=(radii >= min_radius_m),
                                     color=_COL["ok"], alpha=0.25, zorder=1)
        self._ax_radius.fill_between(ch_km, disp, 0,
                                     where=(radii < min_radius_m),
                                     color=_COL["bad"], alpha=0.40, zorder=1)
        self._ax_radius.axhline(min_radius_m, color=_COL["min"],
                                linewidth=1.3, linestyle="--",
                                label=f"Min R = {min_radius_m:.0f} m", zorder=3)

        y_top = max(min_radius_m * 3.0,
                    float(np.percentile(disp, 95))) * 1.1
        self._ax_radius.set_ylim(0, y_top)
        self._ax_radius.set_xlabel("Chainage (km)", color="#94a3b8", fontsize=9)
        self._ax_radius.set_ylabel("Radius (m)",    color="#94a3b8", fontsize=9)
        self._ax_radius.legend(fontsize=8, facecolor="#1e293b",
                               edgecolor="#334155", labelcolor="#e2e8f0",
                               framealpha=0.9)

        title_txt   = f"{'⚠ ' if n_viol else '✓ '}{n_viol} station(s) below min radius"
        title_color = _COL["bad"] if n_viol else _COL["ok"]
        self._ax_radius.set_title(title_txt, color=title_color, fontsize=9)

        self.fig.tight_layout(pad=1.4)
        self.draw()

        finite    = radii[np.isfinite(radii)]
        min_found = float(finite.min()) if len(finite) else float("inf")
        return min_found, n_viol, radii

    def clear(self):
        self._draw_empty()
