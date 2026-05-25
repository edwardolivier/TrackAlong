"""
Construction cost chart tab.

Layout (GridSpec 2×2):
  [0, :]  Horizontal bar chart — one bar per cost category
  [1, 0]  Line-item detail — earthworks + structures
  [1, 1]  Track items + grand total summary
"""
from __future__ import annotations
from typing import List

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.gridspec as mgs

from ..core.costing import CostResult, CostLine

_BG   = "#0f172a"
_PANEL = "#1e293b"
_GRID = "#334155"
_FG   = "#e2e8f0"
_MUTE = "#94a3b8"

_COL_CUT    = "#dc2626"
_COL_FILL   = "#16a34a"
_COL_BRIDGE = "#3b82f6"
_COL_TUNNEL = "#d97706"
_COL_TRACK  = "#0ea5e9"


def _style(ax):
    ax.set_facecolor(_BG)
    ax.tick_params(colors=_MUTE, labelsize=8)
    for sp in ax.spines.values():
        sp.set_edgecolor(_GRID)


def _fmt_m(value: float) -> str:
    """Format dollar value as $XM or $X.XM."""
    if value >= 1e9:
        return f"${value/1e9:.2f} B"
    if value >= 1e6:
        return f"${value/1e6:.1f} M"
    return f"${value/1e3:.0f} k"


def _section_text(title: str, lines: List[CostLine]) -> str:
    rows = [f"▶ {title}"]
    if not lines:
        rows.append("   (none)")
        return "\n".join(rows)
    for ln in lines:
        qty = f"{ln.quantity:>11,.0f} {ln.unit}"
        sub = _fmt_m(ln.subtotal)
        label = ln.label[:28]
        rows.append(f"  {label:<28}  {qty}  {sub:>9}")
    return "\n".join(rows)


class CostWidget(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 5.5), facecolor=_BG)
        super().__init__(self.fig)
        self.setParent(parent)
        self._draw_empty()

    # ------------------------------------------------------------------ public

    def update_cost(self, result: CostResult):
        self.fig.clear()

        gs = mgs.GridSpec(
            2, 2, figure=self.fig,
            height_ratios=[1, 1.8],
            left=0.04, right=0.98,
            top=0.93, bottom=0.04,
            hspace=0.35, wspace=0.12,
        )
        ax_bar   = self.fig.add_subplot(gs[0, :])
        ax_left  = self.fig.add_subplot(gs[1, 0])
        ax_right = self.fig.add_subplot(gs[1, 1])

        _style(ax_bar)
        ax_left.axis("off");  ax_left.set_facecolor(_BG)
        ax_right.axis("off"); ax_right.set_facecolor(_BG)

        # ── Bar chart ─────────────────────────────────────────────────────────
        track_lbl = "Track (double)" if result.double_track else "Track (single)"
        cats   = ["Cut", "Fill", "Bridges", "Tunnels", track_lbl]
        vals   = [
            result.subtotal_cut    / 1e6,
            result.subtotal_fill   / 1e6,
            result.subtotal_bridges / 1e6,
            result.subtotal_tunnels / 1e6,
            result.subtotal_track  / 1e6,
        ]
        colors = [_COL_CUT, _COL_FILL, _COL_BRIDGE, _COL_TUNNEL, _COL_TRACK]
        y      = np.arange(len(cats))

        bars = ax_bar.barh(y, vals, color=colors, height=0.55, alpha=0.88)
        ax_bar.set_yticks(y)
        ax_bar.set_yticklabels(cats, color=_FG, fontsize=9)
        ax_bar.set_xlabel("$M AUD  (pre-contingency)", color=_MUTE, fontsize=8)
        ax_bar.tick_params(colors=_MUTE)
        ax_bar.xaxis.grid(True, color=_GRID, linewidth=0.5, linestyle=":")
        ax_bar.set_axisbelow(True)

        max_val = max(vals) if any(v > 0 for v in vals) else 1.0
        for bar, val in zip(bars, vals):
            if val > 0:
                ax_bar.text(
                    bar.get_width() + max_val * 0.012,
                    bar.get_y() + bar.get_height() / 2,
                    _fmt_m(val * 1e6),
                    va="center", ha="left", color=_MUTE, fontsize=8,
                )

        track_type = "Double track" if result.double_track else "Single track"
        ax_bar.set_title(
            f"Construction Cost Estimate — {result.route_length_km:.1f} km   "
            f"({track_type})   "
            f"TOTAL  {_fmt_m(result.total)}  "
            f"(incl. {result.contingency_pct:.0f}% contingency)",
            color=_FG, fontsize=10, pad=6, loc="left",
        )

        # ── Left panel: earthworks + structures line items ────────────────────
        left_txt = "\n\n".join([
            _section_text("Earthworks — Cut",  result.lines_cut),
            _section_text("Earthworks — Fill", result.lines_fill),
            _section_text("Bridges",           result.lines_bridges),
            _section_text("Tunnels",           result.lines_tunnels),
        ])
        ax_left.text(
            0.01, 0.99, left_txt,
            transform=ax_left.transAxes,
            va="top", ha="left",
            color=_FG, fontsize=7.5,
            fontfamily="monospace",
        )

        # ── Right panel: track + grand total ─────────────────────────────────
        track_txt = _section_text(
            f"Track — {track_type}", result.lines_track
        )

        sep = "─" * 44
        c   = result.contingency_pct
        right_txt = "\n\n".join([
            track_txt,
            "\n".join([
                sep,
                f"  {'Earthworks':<26}  {_fmt_m(result.subtotal_earthworks):>9}",
                f"  {'Bridges':<26}  {_fmt_m(result.subtotal_bridges):>9}",
                f"  {'Tunnels':<26}  {_fmt_m(result.subtotal_tunnels):>9}",
                f"  {'Track':<26}  {_fmt_m(result.subtotal_track):>9}",
                sep,
                f"  {'Sub-total (excl. contingency)':<26}  {_fmt_m(result.subtotal_base):>9}",
                f"  {f'Contingency ({c:.0f}%)':<26}  {_fmt_m(result.contingency_amount):>9}",
                sep,
                f"  {'TOTAL':<26}  {_fmt_m(result.total):>9}",
                f"  {'Per km':<26}  {_fmt_m(result.total / max(result.route_length_km, 0.001))}/km",
            ]),
        ])
        ax_right.text(
            0.01, 0.99, right_txt,
            transform=ax_right.transAxes,
            va="top", ha="left",
            color=_FG, fontsize=7.5,
            fontfamily="monospace",
        )

        self.draw()

    def clear(self):
        self._draw_empty()

    # ------------------------------------------------------------------ private

    def _draw_empty(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(_BG)
        ax.axis("off")
        ax.text(
            0.5, 0.5,
            "Run an analysis to see construction cost estimates.",
            transform=ax.transAxes,
            ha="center", va="center",
            color="#475569", fontsize=11,
        )
        self.draw()
