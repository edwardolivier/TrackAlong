"""
Superelevation (cant) chart — three stacked subplots:
  Top    : Actual cant + equilibrium cant vs chainage (mm)
  Middle : Max permissible speed vs chainage (km/h)
  Bottom : Track twist vs chainage (mm/3m) with limit line
"""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches

_COL = {
    "eq_cant":   "#64748b",   # equilibrium cant (dashed grey)
    "act_cant":  "#38bdf8",   # actual / applied cant
    "cant_def":  "#f59e0b",   # cant deficiency fill
    "speed_ok":  "#22c55e",
    "speed_bad": "#ef4444",
    "twist_ok":  "#a78bfa",
    "twist_bad": "#ef4444",
    "limit":     "#f59e0b",
    "design":    "#334155",
}


class SuperelevationWidget(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 5.5), facecolor="#0f172a")
        super().__init__(self.fig)
        self.setParent(parent)

        gs = self.fig.add_gridspec(3, 1, hspace=0.55,
                                    height_ratios=[2, 1.5, 1.5])
        self._ax_cant  = self.fig.add_subplot(gs[0])
        self._ax_speed = self.fig.add_subplot(gs[1])
        self._ax_twist = self.fig.add_subplot(gs[2])

        self._style_axes()
        self._draw_empty()

    # ------------------------------------------------------------------ style

    def _style_axes(self):
        for ax in (self._ax_cant, self._ax_speed, self._ax_twist):
            ax.set_facecolor("#0f172a")
            ax.tick_params(colors="#94a3b8", labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor("#334155")
        self._ax_cant.set_ylabel("Cant (mm)",     color="#94a3b8", fontsize=9)
        self._ax_speed.set_ylabel("Speed (km/h)", color="#94a3b8", fontsize=9)
        self._ax_twist.set_ylabel("Twist (mm/3m)",color="#94a3b8", fontsize=9)
        self._ax_twist.set_xlabel("Chainage (km)",color="#94a3b8", fontsize=9)
        self.fig.tight_layout(pad=1.2)

    def _draw_empty(self):
        for ax in (self._ax_cant, self._ax_speed, self._ax_twist):
            ax.clear()
        self._style_axes()
        self._ax_cant.text(
            0.5, 0.5,
            "Analyse a route to see the superelevation profile.",
            transform=self._ax_cant.transAxes,
            ha="center", va="center", color="#475569", fontsize=11,
        )
        self.draw()

    # ------------------------------------------------------------------ update

    def update_cant(self, cant_analysis):
        """cant_analysis : CantAnalysis from cant.analyse_cant()"""
        for ax in (self._ax_cant, self._ax_speed, self._ax_twist):
            ax.clear()
        self._style_axes()

        ca   = cant_analysis
        ch_km = ca.chainage / 1000.0
        V     = ca.design_speed_kph

        # ── Top: cant ────────────────────────────────────────────────────────
        # Equilibrium cant (dashed background)
        self._ax_cant.plot(ch_km, ca.equilibrium_cant,
                           color=_COL["eq_cant"], linewidth=1.0,
                           linestyle="--", label="Equilibrium cant", zorder=2)
        # Actual cant (solid)
        self._ax_cant.plot(ch_km, ca.actual_cant,
                           color=_COL["act_cant"], linewidth=1.8,
                           label="Applied cant", zorder=3)
        # Cant deficiency fill (between eq and actual)
        self._ax_cant.fill_between(
            ch_km, ca.actual_cant, ca.equilibrium_cant,
            where=(ca.equilibrium_cant > ca.actual_cant),
            color=_COL["cant_def"], alpha=0.35, label="Cant deficiency", zorder=1,
        )

        # Max cant limit line
        if ca.max_cant_limit_mm > 0:
            self._ax_cant.axhline(ca.max_cant_limit_mm, color=_COL["limit"],
                                  linewidth=1.0, linestyle=":",
                                  label=f"Max cant {ca.max_cant_limit_mm:.0f} mm")

        cant_top = max(float(np.max(ca.equilibrium_cant)) * 1.15, 10.0)
        self._ax_cant.set_ylim(0, cant_top)
        self._ax_cant.set_ylabel("Cant (mm)", color="#94a3b8", fontsize=9)
        self._ax_cant.legend(loc="upper right", fontsize=8,
                             facecolor="#1e293b", edgecolor="#334155",
                             labelcolor="#e2e8f0", framealpha=0.9)
        self._ax_cant.set_title("Superelevation (Cant)", color="#94a3b8",
                                fontsize=9, loc="left")

        # ── Middle: max permissible speed ────────────────────────────────────
        speed_ok  = ca.max_speed >= V * 0.99
        speed_bad = ~speed_ok

        self._ax_speed.plot(ch_km, ca.max_speed, color="#64748b",
                            linewidth=0.8, zorder=2)
        self._ax_speed.fill_between(ch_km, ca.max_speed, 0,
                                    where=speed_ok,
                                    color=_COL["speed_ok"], alpha=0.25, zorder=1)
        self._ax_speed.fill_between(ch_km, ca.max_speed, 0,
                                    where=speed_bad,
                                    color=_COL["speed_bad"], alpha=0.40, zorder=1)
        self._ax_speed.axhline(V, color=_COL["limit"], linewidth=1.2,
                               linestyle="--", label=f"Design {V:.0f} km/h")
        y_top = max(V * 1.1, float(np.max(ca.max_speed)) * 1.05)
        self._ax_speed.set_ylim(0, y_top)
        self._ax_speed.set_ylabel("Speed (km/h)", color="#94a3b8", fontsize=9)

        n_rest = ca.speed_restricted_stations
        title_col = _COL["speed_bad"] if n_rest else _COL["speed_ok"]
        self._ax_speed.set_title(
            f"{'⚠ ' if n_rest else '✓ '}Max permissible speed "
            f"({n_rest} stations below design speed)",
            color=title_col, fontsize=9, loc="left",
        )
        self._ax_speed.legend(loc="lower right", fontsize=8,
                              facecolor="#1e293b", edgecolor="#334155",
                              labelcolor="#e2e8f0", framealpha=0.9)

        # ── Bottom: track twist ───────────────────────────────────────────────
        twist_lim = ca.max_twist_limit_mm
        viol_mask = ca.twist_3m > twist_lim

        self._ax_twist.plot(ch_km, ca.twist_3m, color="#64748b",
                            linewidth=0.9, zorder=2)
        self._ax_twist.fill_between(ch_km, ca.twist_3m, 0,
                                    where=~viol_mask,
                                    color=_COL["twist_ok"], alpha=0.30, zorder=1)
        if np.any(viol_mask):
            self._ax_twist.fill_between(ch_km, ca.twist_3m, 0,
                                        where=viol_mask,
                                        color=_COL["twist_bad"], alpha=0.50,
                                        zorder=2)
        self._ax_twist.axhline(twist_lim, color=_COL["limit"],
                               linewidth=1.2, linestyle="--",
                               label=f"Limit {twist_lim:.1f} mm/3m")

        self._ax_twist.set_ylabel("Twist (mm/3m)", color="#94a3b8", fontsize=9)
        self._ax_twist.set_xlabel("Chainage (km)", color="#94a3b8", fontsize=9)
        self._ax_twist.legend(loc="upper right", fontsize=8,
                              facecolor="#1e293b", edgecolor="#334155",
                              labelcolor="#e2e8f0", framealpha=0.9)
        n_tv = ca.twist_violation_stations
        self._ax_twist.set_title(
            f"{'⚠ ' if n_tv else '✓ '}Track Twist "
            f"({n_tv} stations exceeding limit)",
            color=_COL["twist_bad"] if n_tv else _COL["twist_ok"],
            fontsize=9, loc="left",
        )

        self.fig.tight_layout(pad=1.2)
        self.draw()

    # ------------------------------------------------------------------ clear

    def clear(self):
        self._draw_empty()
