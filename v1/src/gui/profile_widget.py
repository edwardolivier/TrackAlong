"""
Matplotlib profile chart embedded in a Qt widget.
Shows ground profile, proposed track level, cut/fill shading,
and tunnel / bridge structure bands with start/end chainage labels.
"""

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import numpy as np


# Colour palette
_COL = {
    "ground":  "#a16207",
    "track":   "#38bdf8",
    "fill":    "#16a34a",
    "cut":     "#dc2626",
    "tunnel":  "#92400e",   # burnt orange band
    "bridge":  "#1e40af",   # dark blue band
    "grade":   "#475569",
}

# Land zone category → colour
_LAND_COLOURS = {
    "Crown / Conservation":           "#15803d",
    "Rural / Agricultural":           "#65a30d",
    "Residential (low density)":      "#f97316",
    "Residential (med/high density)": "#dc2626",
    "Commercial":                     "#a855f7",
    "Industrial":                     "#64748b",
    "Infrastructure":                 "#0ea5e9",
    "Other":                          "#334155",
}


class ProfileWidget(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(12, 3.8), facecolor="#0f172a")
        super().__init__(self.fig)
        self.setParent(parent)
        self._ax = self.fig.add_subplot(111)
        self._ax2 = self._ax.twinx()
        self._style_axes()
        self._draw_empty()

    # ------------------------------------------------------------------ styling

    def _style_axes(self):
        for ax in (self._ax, self._ax2):
            ax.set_facecolor("#0f172a")
            ax.tick_params(colors="#94a3b8", labelsize=9)
            for spine in ax.spines.values():
                spine.set_edgecolor("#334155")
        self._ax.set_xlabel("Chainage (km)", color="#94a3b8", fontsize=9)
        self._ax.set_ylabel("Elevation (m)", color="#94a3b8", fontsize=9)
        self._ax2.set_ylabel("Grade (%)", color="#475569", fontsize=9)
        self._ax2.tick_params(colors="#475569")
        self.fig.tight_layout(pad=1.4)

    def _draw_empty(self):
        self._ax.clear()
        self._ax2.clear()
        self._style_axes()
        self._ax.text(
            0.5, 0.5,
            "Plot a route and click  Analyse  to see the vertical profile.",
            transform=self._ax.transAxes,
            ha="center", va="center",
            color="#475569", fontsize=11,
        )
        self.draw()

    # ------------------------------------------------------------------ main update

    def update_profile(self, alignment, geology=None, land_zones=None):
        self._ax.clear()
        self._ax2.clear()
        self._style_axes()

        ch_km = alignment.chainage / 1000.0
        g = alignment.ground
        t = alignment.track
        grade = alignment.grade

        # --- 1. Structure bands (drawn first so they sit behind profiles) ---
        ymin, ymax = self._elev_limits(g, t)
        self._draw_structure_bands(alignment, ch_km, ymin, ymax)

        # --- 2. Cut / fill shading ---
        self._ax.fill_between(ch_km, g, t,
                              where=(t > g), interpolate=True,
                              color=_COL["fill"], alpha=0.40, zorder=2)
        self._ax.fill_between(ch_km, g, t,
                              where=(t < g), interpolate=True,
                              color=_COL["cut"], alpha=0.40, zorder=2)

        # --- 3. Ground and track profiles ---
        self._ax.plot(ch_km, g, color=_COL["ground"], linewidth=1.3,
                      label="Ground", zorder=4)
        self._ax.plot(ch_km, t, color=_COL["track"], linewidth=2.0,
                      label="Track", zorder=5)

        # --- 4. Grade (secondary axis) ---
        self._ax2.plot(ch_km, grade, color=_COL["grade"], linewidth=0.8,
                       linestyle="--", alpha=0.7)
        max_g = max(alignment.max_grade_pct, 0.5)
        self._ax2.set_ylim(-max_g * 3, max_g * 3)
        self._ax2.axhline(0, color="#334155", linewidth=0.5, linestyle=":")

        # --- 5. Min track elevation line ---
        min_elev = getattr(alignment, "min_track_elev_m", -1e9)
        if min_elev > -1e8:
            self._ax.axhline(min_elev, color="#a855f7", linewidth=1.3,
                             linestyle="--", alpha=0.85, zorder=6,
                             label=f"Min elev {min_elev:.0f} m")

        # --- 6. Grade violation markers ---
        for ch, _ in alignment.violations:
            self._ax.axvline(ch / 1000, color="#f59e0b",
                             linewidth=1.2, linestyle=":", alpha=0.9, zorder=6)

        # --- 7. Geology strip (drawn before final ylim so we can expand it) ---
        geo_strip_h = 0.0
        if geology is not None and geology.segments:
            geo_strip_h = (ymax - ymin) * 0.06
            self._draw_geology_strip(geology, ch_km, ymin, geo_strip_h)

        # --- 7b. Land zone strip (drawn below geology strip) ---
        land_strip_h = 0.0
        lz_segs = getattr(land_zones, "segments", None) if land_zones is not None else None
        if lz_segs:
            land_strip_h = (ymax - ymin) * 0.06
            self._draw_land_strip(lz_segs, ch_km, ymin - geo_strip_h, land_strip_h)

        # --- 8. Elevation limits ---
        margin = (ymax - ymin) * 0.08
        self._ax.set_ylim(ymin - geo_strip_h - land_strip_h - margin, ymax + margin)

        # --- 9. Legend ---
        self._ax.legend(
            handles=self._legend_handles(alignment, geology, land_zones),
            loc="upper right", fontsize=8,
            facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0",
            framealpha=0.9,
        )

        self._ax.set_xlabel("Chainage (km)", color="#94a3b8", fontsize=9)
        self._ax.set_ylabel("Elevation (m)", color="#94a3b8", fontsize=9)
        self._ax2.set_ylabel("Grade (%)", color="#475569", fontsize=9)

        self.fig.tight_layout(pad=1.4)
        self.draw()

    # ------------------------------------------------------------------ helpers

    def _draw_geology_strip(self, geology, ch_km, y_base, strip_h):
        """Draw a coloured geology band just below the ground profile."""
        import matplotlib.patches as mp
        y0 = y_base - strip_h
        for seg in geology.segments:
            s = seg.start_ch / 1000.0
            e = seg.end_ch   / 1000.0
            rect = mp.FancyBboxPatch(
                (s, y0), e - s, strip_h,
                boxstyle="square,pad=0",
                facecolor=seg.color, alpha=0.75,
                edgecolor="#0f172a", linewidth=0.5,
                zorder=2,
            )
            self._ax.add_patch(rect)
            mid = (s + e) / 2.0
            label = seg.eng_label[:10]
            if e - s > (ch_km[-1] - ch_km[0]) * 0.06:
                self._ax.text(
                    mid, y0 + strip_h * 0.5, label,
                    ha="center", va="center",
                    fontsize=6, color="#e2e8f0", fontweight="bold",
                    zorder=3, clip_on=True,
                )

    def _draw_land_strip(self, segments, ch_km, y_base, strip_h):
        """Draw a coloured land zone band below the geology (or ground) strip."""
        import matplotlib.patches as mp
        y0 = y_base - strip_h
        # Scale segment chainage to match the profile x-axis extent
        strip_total = segments[-1].end_ch_m / 1000.0 if segments else 1.0
        profile_total = float(ch_km[-1])
        scale = profile_total / strip_total if strip_total > 0 else 1.0
        min_label_width = profile_total * 0.05
        for seg in segments:
            s = seg.start_ch_m / 1000.0 * scale
            e = seg.end_ch_m   / 1000.0 * scale
            color = _LAND_COLOURS.get(seg.category, "#334155")
            rect = mp.FancyBboxPatch(
                (s, y0), e - s, strip_h,
                boxstyle="square,pad=0",
                facecolor=color, alpha=0.80,
                edgecolor="#0f172a", linewidth=0.5,
                zorder=2,
            )
            self._ax.add_patch(rect)
            if e - s > min_label_width:
                label = seg.category[:14]
                self._ax.text(
                    (s + e) / 2, y0 + strip_h * 0.5, label,
                    ha="center", va="center",
                    fontsize=5, color="#e2e8f0", fontweight="bold",
                    zorder=3, clip_on=True,
                )

    def _elev_limits(self, ground, track):
        combined = np.concatenate([ground, track])
        return float(np.nanmin(combined)), float(np.nanmax(combined))

    def _draw_structure_bands(self, alignment, ch_km, ymin, ymax):
        """Draw shaded bands and chainage labels for tunnels and bridges."""
        total_km = ch_km[-1]

        for tunnel in alignment.tunnels:
            s_km = tunnel.start_ch / 1000
            e_km = tunnel.end_ch / 1000
            self._ax.axvspan(s_km, e_km,
                             color=_COL["tunnel"], alpha=0.25, zorder=1)
            # Boundary lines
            for x in (s_km, e_km):
                self._ax.axvline(x, color=_COL["tunnel"], linewidth=1.2,
                                 linestyle="-", alpha=0.7, zorder=3)
            # Label centred in band
            mid = (s_km + e_km) / 2
            label = (f"T{tunnel.index}\n"
                     f"{s_km:.2f}–{e_km:.2f} km\n"
                     f"({tunnel.length_m/1000:.2f} km)")
            self._ax.text(mid, ymax, label,
                          ha="center", va="top", fontsize=7,
                          color="#fed7aa", fontweight="bold",
                          bbox=dict(boxstyle="round,pad=0.2",
                                    facecolor="#78350f", alpha=0.75,
                                    edgecolor="none"),
                          zorder=7)

        for bridge in alignment.bridges:
            s_km = bridge.start_ch / 1000
            e_km = bridge.end_ch / 1000
            self._ax.axvspan(s_km, e_km,
                             color=_COL["bridge"], alpha=0.25, zorder=1)
            for x in (s_km, e_km):
                self._ax.axvline(x, color=_COL["bridge"], linewidth=1.2,
                                 linestyle="-", alpha=0.7, zorder=3)
            mid = (s_km + e_km) / 2
            label = (f"B{bridge.index}\n"
                     f"{s_km:.2f}–{e_km:.2f} km\n"
                     f"({bridge.length_m/1000:.2f} km)")
            self._ax.text(mid, ymax, label,
                          ha="center", va="top", fontsize=7,
                          color="#bfdbfe", fontweight="bold",
                          bbox=dict(boxstyle="round,pad=0.2",
                                    facecolor="#1e3a8a", alpha=0.75,
                                    edgecolor="none"),
                          zorder=7)

    def _legend_handles(self, alignment, geology=None, land_zones=None):
        handles = [
            mpatches.Patch(color=_COL["track"], label="Track"),
            mpatches.Patch(color=_COL["ground"], label="Ground"),
            mpatches.Patch(color=_COL["fill"], alpha=0.6, label="Fill (earthwork)"),
            mpatches.Patch(color=_COL["cut"], alpha=0.6, label="Cut (earthwork)"),
        ]
        if alignment.tunnels:
            handles.append(
                mpatches.Patch(color=_COL["tunnel"], alpha=0.5,
                               label=f"Tunnel ×{alignment.num_tunnels}")
            )
        if alignment.bridges:
            handles.append(
                mpatches.Patch(color=_COL["bridge"], alpha=0.5,
                               label=f"Bridge ×{alignment.num_bridges}")
            )
        min_elev = getattr(alignment, "min_track_elev_m", -1e9)
        if min_elev > -1e8:
            handles.append(
                mpatches.Patch(color="#a855f7", alpha=0.8,
                               label=f"Min elev {min_elev:.0f} m")
            )
        if geology is not None and geology.segments:
            seen = set()
            for seg in geology.segments:
                if seg.eng_class not in seen:
                    seen.add(seg.eng_class)
                    handles.append(
                        mpatches.Patch(color=seg.color, alpha=0.75,
                                       label=seg.eng_label)
                    )
        lz_segs = getattr(land_zones, "segments", None) if land_zones is not None else None
        if lz_segs:
            seen = set()
            for seg in lz_segs:
                if seg.category not in seen:
                    seen.add(seg.category)
                    color = _LAND_COLOURS.get(seg.category, "#334155")
                    handles.append(
                        mpatches.Patch(color=color, alpha=0.80,
                                       label=f"Land: {seg.category}")
                    )
        return handles

    def clear(self):
        self._draw_empty()
