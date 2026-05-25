"""
Main application window.
Layout:
  Left sidebar  : ParamsPanel (railway type + geometry + speed/cant constraints)
  Centre top    : MapWidget (Leaflet interactive map)
  Centre bottom : ProfileWidget (vertical profile + cut/fill chart)
                  HorizontalWidget (plan view + radius profile)
                  SuperelevationWidget (cant + speed + twist)
  Right sidebar : Results panel (stats, geometry checks, violations)
"""

import json
import threading
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QPushButton, QLabel, QProgressBar,
    QFrame, QScrollArea, QSizePolicy, QMessageBox, QTabWidget,
    QFileDialog, QApplication,
)
from PySide6.QtCore import Qt, Signal, QObject, Slot
from PySide6.QtGui import QFont, QShortcut, QKeySequence

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from .map_widget import MapWidget
from .profile_widget import ProfileWidget
from .horizontal_widget import HorizontalWidget
from .superelevation_widget import SuperelevationWidget
from .cost_widget import CostWidget
from .params_panel import ParamsPanel
from pathlib import Path
from ..core import elevation, optimizer, route_optimizer
from ..core import cant as cant_module
from ..core import geology as geo_module
from ..core import costing as costing_module
from ..core import land_zoning as land_module
from ..core.optimizer import GeometryParams
from ..core.cant import detect_coincident_curves

_CACHE_DIR = Path(__file__).parent.parent.parent / "cache"


class WorkerSignals(QObject):
    progress = Signal(int, str)
    finished = Signal()
    error    = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TrackAlong — Railway Alignment Analyser")
        self.resize(1440, 920)
        self._waypoints      = []
        self._alignment      = None
        self._params         = {}
        self._pending_result = None
        self._pending_route  = None
        self._land_zone_result = None
        self._params_collapsed  = False
        self._results_collapsed = False
        self._center_expanded   = None   # None | "map" | "charts"
        self._build_ui()
        self._apply_stylesheet()
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            self._escape_expand
        )

    # ------------------------------------------------------------------ UI build

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Outer horizontal splitter — params | centre | results (all resizable)
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setStyleSheet(
            "QSplitter::handle:horizontal {"
            "  background: #334155; width: 4px;"
            "}"
            "QSplitter::handle:horizontal:hover {"
            "  background: #0ea5e9; width: 4px;"
            "}"
        )
        root.addWidget(self._main_splitter)

        # Left sidebar
        self._params_panel = ParamsPanel()
        self._params_panel.params_changed.connect(self._on_params_changed)
        self._main_splitter.addWidget(self._params_panel)

        # Centre: map + charts
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.setStyleSheet("QSplitter::handle { background: #334155; }")

        _EXPAND_BTN_SS = (
            "QPushButton{background:#0f172a;color:#475569;border:none;"
            "border-radius:3px;font-size:13px;padding:0px;}"
            "QPushButton:hover{background:#1e293b;color:#94a3b8;}"
        )

        self._map_wrap = QWidget()
        _mwl = QVBoxLayout(self._map_wrap)
        _mwl.setContentsMargins(0, 0, 0, 0)
        _mwl.setSpacing(0)
        _map_hdr = QWidget()
        _map_hdr.setFixedHeight(28)
        _map_hdr.setStyleSheet("background:#1e293b; border-bottom:1px solid #334155;")
        _mhl = QHBoxLayout(_map_hdr)
        _mhl.setContentsMargins(8, 0, 4, 0)
        _mhl.setSpacing(4)
        _map_lbl = QLabel("Map")
        _map_lbl.setStyleSheet("color:#64748b; font-size:10px; font-weight:600;")
        _mhl.addWidget(_map_lbl)
        _mhl.addStretch()

        _MAP_ACT_SS = (
            "QPushButton{background:#0f172a;color:#64748b;"
            "border:1px solid #283548;border-radius:3px;"
            "font-size:10px;padding:2px 7px;}"
            "QPushButton:hover{background:#1e293b;color:#94a3b8;}"
        )
        _fit_btn = QPushButton("Fit")
        _fit_btn.setToolTip("Zoom map to fit the current route")
        _fit_btn.setStyleSheet(_MAP_ACT_SS)
        _fit_btn.clicked.connect(self._map_widget_fit)
        _mhl.addWidget(_fit_btn)

        _save_btn = QPushButton("Save")
        _save_btn.setToolTip("Save waypoints to a JSON file")
        _save_btn.setStyleSheet(_MAP_ACT_SS)
        _save_btn.clicked.connect(self._save_route)
        _mhl.addWidget(_save_btn)

        _load_btn = QPushButton("Load")
        _load_btn.setToolTip("Load waypoints from a JSON file")
        _load_btn.setStyleSheet(_MAP_ACT_SS)
        _load_btn.clicked.connect(self._load_route)
        _mhl.addWidget(_load_btn)

        self._map_expand_btn = QPushButton("⛶")
        self._map_expand_btn.setFixedSize(22, 20)
        self._map_expand_btn.setToolTip("Expand map  (Esc to restore)")
        self._map_expand_btn.setStyleSheet(_EXPAND_BTN_SS)
        self._map_expand_btn.clicked.connect(lambda: self._toggle_center_expand("map"))
        _mhl.addWidget(self._map_expand_btn)
        _mwl.addWidget(_map_hdr)

        self._map_widget = MapWidget()
        self._map_widget.route_updated.connect(self._on_route_updated)
        _mwl.addWidget(self._map_widget, stretch=1)
        self._splitter.addWidget(self._map_wrap)

        self._bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(self._bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 4, 8, 4)
        tb_layout.setSpacing(8)

        self._optimise_btn = QPushButton("Optimise Route")
        self._optimise_btn.setEnabled(False)
        self._optimise_btn.setToolTip(
            "Automatically find the best corridor between your waypoints."
        )
        self._optimise_btn.setStyleSheet("""
            QPushButton {
                background: #d97706; color: #fff;
                border: none; border-radius: 6px;
                padding: 6px 18px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #f59e0b; }
            QPushButton:disabled { background: #334155; color: #64748b; }
        """)
        self._optimise_btn.clicked.connect(self._run_route_optimiser)
        tb_layout.addWidget(self._optimise_btn)

        self._analyse_btn = QPushButton("Analyse Route")
        self._analyse_btn.setEnabled(False)
        self._analyse_btn.setStyleSheet("""
            QPushButton {
                background: #0ea5e9; color: #fff;
                border: none; border-radius: 6px;
                padding: 6px 18px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #38bdf8; }
            QPushButton:disabled { background: #334155; color: #64748b; }
        """)
        self._analyse_btn.clicked.connect(self._run_analysis)
        tb_layout.addWidget(self._analyse_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-radius: 6px;
                padding: 6px 14px; font-size: 12px;
            }
            QPushButton:hover { background: #334155; }
        """)
        self._clear_btn.clicked.connect(self._clear_all)
        tb_layout.addWidget(self._clear_btn)

        _SEP = QFrame()
        _SEP.setFrameShape(QFrame.Shape.VLine)
        _SEP.setStyleSheet("color: #334155;")
        _SEP.setFixedWidth(1)
        tb_layout.addWidget(_SEP)

        _SB_BTN_SS = (
            "QPushButton{background:#1e293b;color:#64748b;"
            "border:1px solid #283548;border-radius:4px;"
            "font-size:11px;padding:3px 8px;}"
            "QPushButton:hover{background:#1e3a5f;color:#94a3b8;}"
            "QPushButton:checked{background:#0ea5e9;color:#fff;border:none;}"
        )
        self._params_toggle_btn = QPushButton("◀  Params")
        self._params_toggle_btn.setToolTip("Hide / show parameters panel")
        self._params_toggle_btn.setStyleSheet(_SB_BTN_SS)
        self._params_toggle_btn.clicked.connect(self._toggle_params)
        tb_layout.addWidget(self._params_toggle_btn)

        self._results_toggle_btn = QPushButton("Results  ▶")
        self._results_toggle_btn.setToolTip("Hide / show results panel")
        self._results_toggle_btn.setStyleSheet(_SB_BTN_SS)
        self._results_toggle_btn.clicked.connect(self._toggle_results)
        tb_layout.addWidget(self._results_toggle_btn)

        self._status_label = QLabel("Plot a route on the map, then click Analyse Route.")
        self._status_label.setStyleSheet("color: #64748b; font-size: 11px;")
        tb_layout.addWidget(self._status_label, stretch=1)

        self._charts_expand_btn = QPushButton("⛶")
        self._charts_expand_btn.setFixedSize(24, 24)
        self._charts_expand_btn.setToolTip("Expand charts  (Esc to restore)")
        self._charts_expand_btn.setStyleSheet(
            "QPushButton{background:#1e293b;color:#475569;border:1px solid #334155;"
            "border-radius:3px;font-size:13px;padding:0px;}"
            "QPushButton:hover{background:#334155;color:#94a3b8;}"
        )
        self._charts_expand_btn.clicked.connect(
            lambda: self._toggle_center_expand("charts")
        )
        tb_layout.addWidget(self._charts_expand_btn)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMaximumWidth(200)
        self._progress.setMaximumHeight(14)
        self._progress.setStyleSheet("""
            QProgressBar { background: #1e293b; border: 1px solid #334155;
                           border-radius: 3px; text-align: center; font-size: 9px; }
            QProgressBar::chunk { background: #0ea5e9; border-radius: 3px; }
        """)
        tb_layout.addWidget(self._progress)
        bottom_layout.addWidget(toolbar)

        # Chart tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #334155; background: #0f172a; }
            QTabBar::tab {
                background: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-bottom: none;
                padding: 5px 16px; font-size: 11px;
            }
            QTabBar::tab:selected { background: #0f172a; color: #e2e8f0; }
            QTabBar::tab:hover    { background: #334155; }
        """)

        _tb_style = (
            "QToolBar { background: #1e293b; border: none; spacing: 2px; }"
            "QToolButton { background: #1e293b; color: #94a3b8; border: none;"
            "              border-radius: 3px; padding: 3px; }"
            "QToolButton:hover { background: #334155; }"
            "QToolButton:checked { background: #0ea5e9; color: #fff; }"
        )

        def _tab_container(widget, parent_widget):
            tb = NavigationToolbar2QT(widget, parent_widget)
            tb.setStyleSheet(_tb_style)
            tb.setMaximumHeight(28)
            c = QWidget()
            cl = QVBoxLayout(c)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            cl.addWidget(tb)
            cl.addWidget(widget, stretch=1)
            return c

        self._profile_widget = ProfileWidget()
        self._profile_widget.setMinimumHeight(160)
        self._tabs.addTab(_tab_container(self._profile_widget, self._bottom_widget),
                          "Vertical Profile")

        self._horiz_widget = HorizontalWidget()
        self._horiz_widget.setMinimumHeight(160)
        self._tabs.addTab(_tab_container(self._horiz_widget, self._bottom_widget),
                          "Horizontal Alignment")

        self._superelev_widget = SuperelevationWidget()
        self._superelev_widget.setMinimumHeight(160)
        self._tabs.addTab(_tab_container(self._superelev_widget, self._bottom_widget),
                          "Superelevation")

        self._cost_widget = CostWidget()
        self._cost_widget.setMinimumHeight(160)
        self._tabs.addTab(_tab_container(self._cost_widget, self._bottom_widget),
                          "Cost Estimate")

        bottom_layout.addWidget(self._tabs, stretch=1)
        self._splitter.addWidget(self._bottom_widget)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)
        self._main_splitter.addWidget(self._splitter)

        self._results_panel = self._build_results_panel()
        self._main_splitter.addWidget(self._results_panel)

        # Centre panel stretches; sidebars keep a preferred initial size
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        self._main_splitter.setStretchFactor(2, 0)
        self._main_splitter.setSizes([270, 900, 270])

    # ------------------------------------------------------------------ results panel

    def _build_results_panel(self):
        # Outer container — width is now set by the main horizontal splitter
        container = QWidget()
        container.setMinimumWidth(180)
        outer_layout = QVBoxLayout(container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── Thin header with Copy button ──────────────────────────────────────
        _res_hdr = QWidget()
        _res_hdr.setFixedHeight(26)
        _res_hdr.setStyleSheet("background:#1e293b; border-bottom:1px solid #334155;")
        _rhl = QHBoxLayout(_res_hdr)
        _rhl.setContentsMargins(8, 0, 4, 0)
        _res_title_lbl = QLabel("Results")
        _res_title_lbl.setStyleSheet("color:#64748b; font-size:10px; font-weight:600;")
        _rhl.addWidget(_res_title_lbl)
        _rhl.addStretch()
        _copy_btn = QPushButton("Copy")
        _copy_btn.setToolTip("Copy summary to clipboard")
        _copy_btn.setStyleSheet(
            "QPushButton{background:#0f172a;color:#64748b;"
            "border:1px solid #283548;border-radius:3px;"
            "font-size:10px;padding:2px 7px;}"
            "QPushButton:hover{background:#1e293b;color:#94a3b8;}"
        )
        _copy_btn.clicked.connect(self._copy_results)
        _rhl.addWidget(_copy_btn)
        outer_layout.addWidget(_res_hdr)

        # ── Scroll area ───────────────────────────────────────────────────────
        panel = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: #0f172a; }"
            "QScrollBar:vertical { background: #1e293b; width: 6px; }"
            "QScrollBar::handle:vertical { background: #334155; border-radius: 3px; }"
        )
        outer_layout.addWidget(scroll, stretch=1)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Waypoints ─────────────────────────────────────────────────────────
        self._wp_section_title = QLabel("Waypoints")
        self._wp_section_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._wp_section_title.setStyleSheet("color: #38bdf8; margin-top: 4px;")
        layout.addWidget(self._wp_section_title)
        _wp_sep = QFrame()
        _wp_sep.setFrameShape(QFrame.Shape.HLine)
        _wp_sep.setStyleSheet("color: #334155;")
        layout.addWidget(_wp_sep)

        self._wp_list_widget = QWidget()
        self._wp_list_layout = QVBoxLayout(self._wp_list_widget)
        self._wp_list_layout.setContentsMargins(0, 0, 0, 0)
        self._wp_list_layout.setSpacing(1)
        layout.addWidget(self._wp_list_widget)

        _wp_action_row = QWidget()
        _wal = QHBoxLayout(_wp_action_row)
        _wal.setContentsMargins(0, 2, 0, 2)
        _wal.setSpacing(6)
        _wp_fit_btn = QPushButton("Fit Map")
        _wp_fit_btn.setToolTip("Zoom map to fit the current route / track")
        _wp_fit_btn.setStyleSheet(
            "QPushButton{background:#1e293b;color:#64748b;"
            "border:1px solid #334155;border-radius:4px;"
            "font-size:10px;padding:3px 8px;}"
            "QPushButton:hover{background:#334155;color:#e2e8f0;}"
        )
        _wp_fit_btn.clicked.connect(self._map_widget_fit)
        _wal.addWidget(_wp_fit_btn)
        _wal.addStretch()
        layout.addWidget(_wp_action_row)
        self._refresh_waypoint_list()   # populate "No waypoints yet" state

        def section_title(text):
            lbl = QLabel(text)
            lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            lbl.setStyleSheet("color: #38bdf8; margin-top: 4px;")
            return lbl

        def hsep():
            f = QFrame()
            f.setFrameShape(QFrame.Shape.HLine)
            f.setStyleSheet("color: #334155;")
            return f

        def stat_row(label, attr, color="#e2e8f0"):
            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #64748b; font-size: 11px;")
            val = QLabel("—")
            val.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            rl.addWidget(lbl, stretch=1)
            rl.addWidget(val)
            setattr(self, attr, val)
            return row

        # ── Earthworks ────────────────────────────────────────────────────────
        layout.addWidget(section_title("Earthworks"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Route length",   "_res_length"))
        layout.addWidget(stat_row("Stations",       "_res_stations"))
        layout.addWidget(stat_row("Max grade",      "_res_maxgrade"))
        layout.addWidget(stat_row("Ruling grade",   "_res_ruling",   "#a78bfa"))
        layout.addWidget(stat_row("Grade comp.",    "_res_comp",     "#64748b"))
        layout.addWidget(stat_row("Cut volume",     "_res_cut",      "#fca5a5"))
        layout.addWidget(stat_row("Fill volume",    "_res_fill",     "#86efac"))
        layout.addWidget(stat_row("Net (cut−fill)", "_res_net"))
        layout.addWidget(stat_row("Balance ratio",  "_res_ratio"))

        # ── Horizontal & speed ────────────────────────────────────────────────
        layout.addWidget(section_title("Horizontal & Speed"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Min radius found",     "_res_min_radius", "#a78bfa"))
        layout.addWidget(stat_row("Below min radius",     "_res_radius_viol","#f59e0b"))
        layout.addWidget(stat_row("Design speed",         "_res_design_spd", "#38bdf8"))
        layout.addWidget(stat_row("Min speed on route",   "_res_min_spd",    "#f59e0b"))
        layout.addWidget(stat_row("Speed-restricted sta.","_res_spd_rest",   "#f59e0b"))
        layout.addWidget(stat_row("Curves found",         "_res_curves",     "#94a3b8"))
        layout.addWidget(stat_row("Transition short",     "_res_trans_viol", "#ef4444"))
        layout.addWidget(stat_row("Reverse curve viol.",  "_res_rev_viol",   "#ef4444"))

        # ── Track geometry checks ─────────────────────────────────────────────
        layout.addWidget(section_title("Geometry Checks"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Track twist viol.", "_res_twist_viol", "#ef4444"))
        layout.addWidget(stat_row("Coincident V+H",   "_res_coinc_viol", "#ef4444"))

        # ── Geology ───────────────────────────────────────────────────────────
        layout.addWidget(section_title("Geology"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Hard Rock (A)",   "_res_geo_A", "#b91c1c"))
        layout.addWidget(stat_row("Medium Rock (B)", "_res_geo_B", "#c2410c"))
        layout.addWidget(stat_row("Weak Rock (C)",   "_res_geo_C", "#a16207"))
        layout.addWidget(stat_row("Soft Ground (D)", "_res_geo_D", "#15803d"))
        layout.addWidget(stat_row("Geo-adj cut vol", "_res_geo_cut",  "#fca5a5"))
        layout.addWidget(stat_row("Geo-adj fill vol", "_res_geo_fill", "#86efac"))

        self._geo_risk_label = QLabel("—")
        self._geo_risk_label.setWordWrap(True)
        self._geo_risk_label.setStyleSheet(
            "color: #fbbf24; font-size: 9px; background: #1c1000; "
            "border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self._geo_risk_label)

        # ── Tunnels ───────────────────────────────────────────────────────────
        layout.addWidget(section_title("Tunnels"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Count",        "_res_tun_count", "#fed7aa"))
        layout.addWidget(stat_row("Total length", "_res_tun_len",   "#fed7aa"))
        layout.addWidget(stat_row("Est. volume",  "_res_tun_vol",   "#fed7aa"))

        self._tunnel_detail = QLabel("—")
        self._tunnel_detail.setWordWrap(True)
        self._tunnel_detail.setStyleSheet(
            "color: #92400e; font-size: 9px; background: #1c0a00; "
            "border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self._tunnel_detail)

        # ── Bridges ───────────────────────────────────────────────────────────
        layout.addWidget(section_title("Bridges / Viaducts"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Count",        "_res_bri_count", "#bfdbfe"))
        layout.addWidget(stat_row("Total length", "_res_bri_len",   "#bfdbfe"))
        layout.addWidget(stat_row("Est. volume",  "_res_bri_vol",   "#bfdbfe"))

        self._bridge_detail = QLabel("—")
        self._bridge_detail.setWordWrap(True)
        self._bridge_detail.setStyleSheet(
            "color: #1e40af; font-size: 9px; background: #00061c; "
            "border-radius: 4px; padding: 4px;"
        )
        layout.addWidget(self._bridge_detail)

        # ── Cost Summary ──────────────────────────────────────────────────────
        layout.addWidget(section_title("Construction Cost"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Route length",   "_res_cost_km",     "#a5f3fc"))
        layout.addWidget(stat_row("Single track",   "_res_cost_single",  "#67e8f9"))
        layout.addWidget(stat_row("Double track",   "_res_cost_double",  "#22d3ee"))
        layout.addWidget(stat_row("Earthworks",     "_res_cost_earth",   "#94a3b8"))
        layout.addWidget(stat_row("Bridges",        "_res_cost_bridges", "#94a3b8"))
        layout.addWidget(stat_row("Tunnels",        "_res_cost_tunnels", "#94a3b8"))
        layout.addWidget(stat_row("Track (single)", "_res_cost_track",   "#94a3b8"))

        self._cost_note_label = QLabel("See Cost Estimate tab for full breakdown.")
        self._cost_note_label.setStyleSheet("color: #475569; font-size: 9px;")
        layout.addWidget(self._cost_note_label)

        # ── Land Acquisition ──────────────────────────────────────────────────
        layout.addWidget(section_title("Land Acquisition"))
        layout.addWidget(hsep())
        layout.addWidget(stat_row("Corridor width",  "_res_land_corridor", "#a5f3fc"))
        layout.addWidget(stat_row("Total area",      "_res_land_area",     "#67e8f9"))
        layout.addWidget(stat_row("Total cost",      "_res_land_total",    "#22d3ee"))

        # Per-zone breakdown table (rebuilt dynamically after each analysis)
        self._land_zone_table = QWidget()
        _lztl = QVBoxLayout(self._land_zone_table)
        _lztl.setContentsMargins(0, 0, 0, 0)
        _lztl.setSpacing(1)
        layout.addWidget(self._land_zone_table)

        self._land_note_label = QLabel(
            "Enable Land Acquisition in Parameters to include zoning costs."
        )
        self._land_note_label.setWordWrap(True)
        self._land_note_label.setStyleSheet("color: #475569; font-size: 9px;")
        layout.addWidget(self._land_note_label)

        # ── Violations ────────────────────────────────────────────────────────
        layout.addWidget(section_title("Violations"))
        layout.addWidget(hsep())
        self._violations_label = QLabel("—")
        self._violations_label.setWordWrap(True)
        self._violations_label.setStyleSheet("color: #f59e0b; font-size: 10px;")
        layout.addWidget(self._violations_label)

        layout.addStretch()
        return container

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #0f172a; color: #e2e8f0; }
            QLabel { color: #e2e8f0; }
            QGroupBox { color: #94a3b8; }
            QSplitter { background: #0f172a; }
        """)

    # ------------------------------------------------------------------ slots

    @Slot(list)
    def _on_route_updated(self, waypoints):
        self._waypoints = waypoints
        n = len(waypoints)
        self._analyse_btn.setEnabled(n >= 2)
        self._optimise_btn.setEnabled(n >= 2)
        self._refresh_waypoint_list()
        if n >= 2:
            self._status_label.setText(
                f"{n} waypoints — Optimise Route to auto-find corridor, "
                f"or Analyse Route to evaluate current route."
            )
        else:
            self._status_label.setText("Add at least 2 waypoints on the map.")

    @Slot(dict)
    def _on_params_changed(self, params):
        self._params = params

    # ------------------------------------------------------------------ route optimiser

    def _run_route_optimiser(self):
        if len(self._waypoints) < 2:
            return

        params_dict    = self._params or self._params_panel.get_params()
        corridor_params = self._params_panel.get_route_params()

        self._optimise_btn.setEnabled(False)
        self._analyse_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_label.setText("Starting route optimisation…")

        signals = WorkerSignals()
        signals.progress.connect(self._on_progress)
        signals.finished.connect(self._on_optimise_done)
        signals.error.connect(self._on_analysis_error)

        waypoints = self._waypoints[:]
        max_grade = params_dict.get("max_grade_pct", 1.0)

        def worker():
            try:
                result = route_optimizer.optimise_corridor(
                    waypoints, corridor_params, max_grade,
                    lambda msg: signals.progress.emit(50, msg)
                )
                self._pending_route = result
                signals.finished.emit()
            except Exception as exc:
                signals.error.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    @Slot()
    def _on_optimise_done(self):
        route = self._pending_route
        if not route:
            self._optimise_btn.setEnabled(True)
            self._analyse_btn.setEnabled(True)
            self._progress.setVisible(False)
            return
        self._waypoints = [[lat, lon] for lat, lon in route]
        self._map_widget.set_optimised_route(route)
        self._optimise_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status_label.setText(
            f"Optimal corridor found: {len(route)} waypoints. Running analysis…"
        )
        self._run_analysis()

    # ------------------------------------------------------------------ analysis

    def _run_analysis(self):
        if len(self._waypoints) < 2:
            return

        params_dict    = self._params or self._params_panel.get_params()
        land_params    = self._params_panel.get_land_params()
        interval_m     = params_dict.get("interval_m", 10)
        query_interval = max(interval_m * 5, 50)

        self._analyse_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_label.setText("Fetching elevation data…")

        signals = WorkerSignals()
        signals.progress.connect(self._on_progress)
        signals.finished.connect(self._on_analysis_done)
        signals.error.connect(self._on_analysis_error)

        waypoints = self._waypoints[:]
        geom = GeometryParams(
            max_grade_pct               = params_dict["max_grade_pct"],
            k_crest                     = params_dict["k_crest"],
            k_sag                       = params_dict["k_sag"],
            formation_width_m           = params_dict["formation_width_m"],
            batter_cut                  = params_dict["batter_cut"],
            batter_fill                 = params_dict["batter_fill"],
            cut_trigger_m               = params_dict.get("cut_trigger_m", 50.0),
            fill_trigger_m              = params_dict.get("fill_trigger_m", 10.0),
            min_track_elev_m            = params_dict.get("min_track_elev_m", -1e9),
            design_speed_kph            = params_dict.get("design_speed_kph", 115.0),
            gauge_mm                    = params_dict.get("gauge_mm", 1435.0),
            max_cant_mm                 = params_dict.get("max_cant_mm", 100.0),
            max_cant_deficiency_mm      = params_dict.get("max_cant_deficiency_mm", 75.0),
            cant_gradient_max_mm_per_m  = params_dict.get("cant_gradient_max_mm_per_m", 2.25),
            max_twist_mm_per_3m         = params_dict.get("max_twist_mm_per_3m", 7.0),
            ruling_grade_length_km      = params_dict.get("ruling_grade_length_km", 10.0),
        )
        min_radius_m = params_dict.get("min_radius_m", 400.0)

        def worker():
            try:
                # 1. Elevation profile
                profile = elevation.fetch_profile(
                    waypoints,
                    query_interval_m=int(query_interval),
                    output_interval_m=int(interval_m),
                    progress_callback=lambda v, msg: signals.progress.emit(v, msg),
                )

                # 2. Horizontal geometry
                signals.progress.emit(52, "Computing horizontal geometry…")
                radii = cant_module.compute_radii(profile)

                # 3. Geology along profile (Macrostrat API, cached)
                signals.progress.emit(55, "Fetching geology data…")
                try:
                    geology = geo_module.fetch_geology(
                        profile, _CACHE_DIR,
                        progress_callback=lambda pct, msg: signals.progress.emit(
                            55 + int(pct * 0.05), msg
                        ),
                    )
                except Exception as geo_exc:
                    geology = None
                    import logging
                    logging.getLogger(__name__).warning(
                        "Geology fetch failed: %s", geo_exc
                    )

                # 4. Vertical alignment with grade compensation + geology batters
                signals.progress.emit(62, "Running vertical alignment optimiser…")
                alignment = optimizer.optimise(profile, geom, radii=radii,
                                               geology=geology)
                alignment._profile   = profile
                alignment._radii     = radii
                alignment._min_r     = min_radius_m
                alignment._geology   = geology

                # 4. Cant / speed / twist / transition analysis
                signals.progress.emit(85, "Running cant and speed analysis…")
                cant_result = cant_module.analyse_cant(
                    profile[:, 0], radii, geom
                )
                alignment._cant = cant_result

                # 5. Coincident V+H curve detection
                coinc = detect_coincident_curves(
                    alignment.grade, profile[:, 0], radii, min_radius_m
                )
                alignment.coincident_curve_violations = [
                    (v.chainage_m, v.description) for v in coinc
                ]

                # 6. Cost estimate (uses geology + alignment — fast, no network)
                signals.progress.emit(93, "Estimating construction costs…")
                try:
                    cost_bands   = self._params_panel.get_cost_bands()
                    double_track = self._params_panel.is_double_track()
                    alignment._cost = costing_module.estimate_costs(
                        alignment, geology, cost_bands, double_track=double_track
                    )
                except Exception as cost_exc:
                    import logging
                    logging.getLogger(__name__).warning("Cost estimate failed: %s", cost_exc)
                    alignment._cost = None

                # 7. Land acquisition zoning (optional — fetches OSM data)
                alignment._land_zones = None
                alignment._land_zones_error = None
                if land_params.get("enabled"):
                    signals.progress.emit(97, "Fetching OSM land-use data…")
                    try:
                        alignment._land_zones = land_module.analyse_land_zones(
                            route_latlng=waypoints,
                            corridor_m=land_params["corridor_m"],
                            category_costs=land_params["category_costs"],
                            progress_callback=lambda msg: signals.progress.emit(97, msg),
                        )
                    except Exception as lz_exc:
                        import logging
                        logging.getLogger(__name__).warning(
                            "Land zone analysis failed: %s", lz_exc
                        )
                        alignment._land_zones_error = str(lz_exc)

                self._pending_result = alignment
                signals.finished.emit()
            except Exception as exc:
                signals.error.emit(str(exc))

        threading.Thread(target=worker, daemon=True).start()

    @Slot(int, str)
    def _on_progress(self, value, msg):
        self._progress.setValue(value)
        self._status_label.setText(msg)

    @Slot()
    def _on_analysis_done(self):
        alignment = self._pending_result
        if alignment is None:
            return
        self._alignment = alignment
        self._progress.setVisible(False)
        self._analyse_btn.setEnabled(True)
        self._tabs.setCurrentIndex(0)   # jump to Vertical Profile
        try:
            self._populate_results(alignment)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._status_label.setText(f"Display error: {exc}")

    # ------------------------------------------------------------------ populate results

    def _populate_results(self, alignment):
        cant    = getattr(alignment, "_cant", None)
        radii   = getattr(alignment, "_radii", None)
        min_r   = getattr(alignment, "_min_r", 400.0)
        geology = getattr(alignment, "_geology", None)

        # ── Earthworks ────────────────────────────────────────────────────────
        length_km = alignment.chainage[-1] / 1000
        self._res_length.setText(f"{length_km:.1f} km")
        self._res_stations.setText(f"{len(alignment.chainage):,}")
        self._res_maxgrade.setText(f"{alignment.max_grade_pct:.3f} %")
        self._res_ruling.setText(f"{alignment.ruling_grade_pct:.3f} %")
        comp_txt = "Yes ✓" if alignment.grade_compensation_applied else "No"
        comp_col = "#22c55e" if alignment.grade_compensation_applied else "#64748b"
        self._res_comp.setText(comp_txt)
        self._res_comp.setStyleSheet(
            f"color: {comp_col}; font-size: 12px; font-weight: 600;"
        )
        self._res_cut.setText(f"{alignment.total_cut_m3 / 1e6:.3f} Mm³")
        self._res_fill.setText(f"{alignment.total_fill_m3 / 1e6:.3f} Mm³")
        net   = alignment.total_cut_m3 - alignment.total_fill_m3
        self._res_net.setText(f"{net / 1e6:+.3f} Mm³")
        ratio = (alignment.total_cut_m3 / alignment.total_fill_m3
                 if alignment.total_fill_m3 > 0 else float("inf"))
        self._res_ratio.setText(f"{ratio:.2f}" if ratio < 1e8 else "∞")

        # ── Horizontal & speed ────────────────────────────────────────────────
        try:
            min_r_found, n_viol, _ = self._horiz_widget.update_alignment(
                alignment._profile, min_r,
                radii=radii, cant_analysis=cant,
            )
            if min_r_found < 1e9:
                self._res_min_radius.setText(f"{min_r_found:,.0f} m")
            else:
                self._res_min_radius.setText("∞ (straight)")
            ok_col = "#22c55e" if n_viol == 0 else "#f59e0b"
            self._res_radius_viol.setText(
                f"{n_viol} stations" if n_viol > 0 else "None ✓"
            )
            self._res_radius_viol.setStyleSheet(
                f"color: {ok_col}; font-size: 12px; font-weight: 600;"
            )
        except Exception as exc:
            self._status_label.setText(f"Horizontal chart error: {exc}")

        if cant is not None:
            V = cant.design_speed_kph
            self._res_design_spd.setText(f"{V:.0f} km/h")
            self._res_min_spd.setText(f"{cant.min_speed_kph:.0f} km/h")
            spd_ok = cant.speed_restricted_stations == 0
            self._res_spd_rest.setText(
                f"{cant.speed_restricted_stations} stations"
                if cant.speed_restricted_stations else "None ✓"
            )
            self._res_spd_rest.setStyleSheet(
                f"color: {'#22c55e' if spd_ok else '#ef4444'}; "
                "font-size: 12px; font-weight: 600;"
            )
            self._res_curves.setText(str(len(cant.curves)))
            tv = cant.transition_violation_count
            self._res_trans_viol.setText(
                f"{tv} curves" if tv else "None ✓"
            )
            self._res_trans_viol.setStyleSheet(
                f"color: {'#22c55e' if tv == 0 else '#ef4444'}; "
                "font-size: 12px; font-weight: 600;"
            )
            rv = cant.reverse_violation_count
            self._res_rev_viol.setText(
                f"{rv} locations" if rv else "None ✓"
            )
            self._res_rev_viol.setStyleSheet(
                f"color: {'#22c55e' if rv == 0 else '#ef4444'}; "
                "font-size: 12px; font-weight: 600;"
            )

        # ── Geometry checks ───────────────────────────────────────────────────
        if cant is not None:
            tw = cant.twist_violation_stations
            self._res_twist_viol.setText(
                f"{tw} stations" if tw else "None ✓"
            )
            self._res_twist_viol.setStyleSheet(
                f"color: {'#22c55e' if tw == 0 else '#ef4444'}; "
                "font-size: 12px; font-weight: 600;"
            )

        coinc = getattr(alignment, "coincident_curve_violations", [])
        nc = len(coinc)
        self._res_coinc_viol.setText(f"{nc} locations" if nc else "None ✓")
        self._res_coinc_viol.setStyleSheet(
            f"color: {'#22c55e' if nc == 0 else '#ef4444'}; "
            "font-size: 12px; font-weight: 600;"
        )

        # ── Geology ───────────────────────────────────────────────────────────
        if geology is not None and geology.any_data:
            lbc = geology.length_by_class
            for cls, attr in (("A", "_res_geo_A"), ("B", "_res_geo_B"),
                               ("C", "_res_geo_C"), ("D", "_res_geo_D")):
                km = lbc.get(cls, 0.0) / 1000.0
                getattr(self, attr).setText(f"{km:.1f} km" if km > 0 else "—")
            if alignment.geology_applied:
                self._res_geo_cut.setText(
                    f"{alignment.geology_adjusted_cut_m3 / 1e6:.3f} Mm³"
                )
                self._res_geo_fill.setText(
                    f"{alignment.geology_adjusted_fill_m3 / 1e6:.3f} Mm³"
                )
            else:
                self._res_geo_cut.setText("—")
                self._res_geo_fill.setText("—")
            risks = geology.risk_notes
            if risks:
                self._geo_risk_label.setText("\n".join(f"⚠ {r}" for r in risks[:4]))
                self._geo_risk_label.setStyleSheet(
                    "color: #fbbf24; font-size: 9px; background: #1c1000; "
                    "border-radius: 4px; padding: 4px;"
                )
            else:
                self._geo_risk_label.setText("No significant risks identified.")
                self._geo_risk_label.setStyleSheet(
                    "color: #22c55e; font-size: 9px; background: #0f172a; padding: 2px;"
                )
        else:
            for attr in ("_res_geo_A", "_res_geo_B", "_res_geo_C", "_res_geo_D",
                         "_res_geo_cut", "_res_geo_fill"):
                getattr(self, attr).setText("No data")
            self._geo_risk_label.setText("Geology data unavailable for this location.")

        # ── Tunnels ───────────────────────────────────────────────────────────
        self._res_tun_count.setText(str(alignment.num_tunnels))
        self._res_tun_len.setText(f"{alignment.total_tunnel_length_m / 1000:.3f} km")
        self._res_tun_vol.setText(f"{alignment.total_tunnel_volume_m3 / 1e6:.3f} Mm³")
        if alignment.tunnels:
            detail = "\n".join(
                f"T{t.index}: {t.start_ch/1000:.2f}–{t.end_ch/1000:.2f} km  "
                f"({t.length_m:.0f} m)  max cut {t.max_depth:.0f} m"
                for t in alignment.tunnels
            )
            self._tunnel_detail.setText(detail)
            self._tunnel_detail.setStyleSheet(
                "color: #fed7aa; font-size: 9px; background: #1c0a00; "
                "border-radius: 4px; padding: 4px;"
            )
        else:
            self._tunnel_detail.setText("None")
            self._tunnel_detail.setStyleSheet(
                "color: #64748b; font-size: 9px; background: #0f172a; padding: 2px;"
            )

        # ── Bridges ───────────────────────────────────────────────────────────
        self._res_bri_count.setText(str(alignment.num_bridges))
        self._res_bri_len.setText(f"{alignment.total_bridge_length_m / 1000:.3f} km")
        self._res_bri_vol.setText(f"{alignment.total_bridge_volume_m3 / 1e6:.3f} Mm³")
        if alignment.bridges:
            detail = "\n".join(
                f"B{b.index}: {b.start_ch/1000:.2f}–{b.end_ch/1000:.2f} km  "
                f"({b.length_m:.0f} m)  max fill {b.max_depth:.0f} m"
                for b in alignment.bridges
            )
            self._bridge_detail.setText(detail)
            self._bridge_detail.setStyleSheet(
                "color: #bfdbfe; font-size: 9px; background: #00061c; "
                "border-radius: 4px; padding: 4px;"
            )
        else:
            self._bridge_detail.setText("None")
            self._bridge_detail.setStyleSheet(
                "color: #64748b; font-size: 9px; background: #0f172a; padding: 2px;"
            )

        # ── Construction Cost summary ─────────────────────────────────────────
        cost = getattr(alignment, "_cost", None)
        if cost is not None:
            bands = self._params_panel.get_cost_bands()
            cost_s = costing_module.estimate_costs(alignment, geology, bands, double_track=False)
            cost_d = costing_module.estimate_costs(alignment, geology, bands, double_track=True)
            self._res_cost_km.setText(f"{cost_s.route_length_km:.1f} km")
            self._res_cost_single.setText(f"${cost_s.total/1e6:.0f} M  (${cost_s.total/max(cost_s.route_length_km,0.001)/1e6:.1f} M/km)")
            self._res_cost_double.setText(f"${cost_d.total/1e6:.0f} M  (${cost_d.total/max(cost_d.route_length_km,0.001)/1e6:.1f} M/km)")
            self._res_cost_earth.setText(f"${cost_s.subtotal_earthworks/1e6:.0f} M")
            self._res_cost_bridges.setText(f"${cost_s.subtotal_bridges/1e6:.0f} M")
            self._res_cost_tunnels.setText(f"${cost_s.subtotal_tunnels/1e6:.0f} M")
            self._res_cost_track.setText(f"${cost_s.subtotal_track/1e6:.0f} M")
        else:
            for a in ("_res_cost_km", "_res_cost_single", "_res_cost_double",
                      "_res_cost_earth", "_res_cost_bridges",
                      "_res_cost_tunnels", "_res_cost_track"):
                getattr(self, a).setText("—")

        # ── Land Acquisition ──────────────────────────────────────────────────
        land     = getattr(alignment, "_land_zones", None)
        land_err = getattr(alignment, "_land_zones_error", None)
        self._populate_land_results(land, land_err)

        # ── Violations (grade + geometry combined) ────────────────────────────
        all_viols = list(alignment.violations)
        for ch, desc in coinc[:3]:
            all_viols.append((ch, desc))
        if cant is not None:
            for rv in cant.reverse_violations[:2]:
                all_viols.append((rv.start_ch,
                    f"Reverse curve: tangent {rv.tangent_length_m:.0f} m "
                    f"< required {rv.required_m:.0f} m"))
        if all_viols:
            vt = "\n".join(f"⚠ ch {int(ch)/1000:.2f} km: {desc}"
                           for ch, desc in all_viols[:8])
            self._violations_label.setText(vt)
        else:
            self._violations_label.setText("None ✓")

        self._status_label.setText(
            f"Done — Cut {alignment.total_cut_m3/1e6:.2f} Mm³  |  "
            f"Fill {alignment.total_fill_m3/1e6:.2f} Mm³  |  "
            f"Tunnels {alignment.num_tunnels}  |  Bridges {alignment.num_bridges}  |  "
            f"Min speed {cant.min_speed_kph:.0f} km/h"
            if cant else
            f"Done — Cut {alignment.total_cut_m3/1e6:.2f} Mm³  |  "
            f"Fill {alignment.total_fill_m3/1e6:.2f} Mm³  |  "
            f"Tunnels {alignment.num_tunnels}  |  Bridges {alignment.num_bridges}"
        )

        # ── Charts ────────────────────────────────────────────────────────────
        try:
            self._profile_widget.update_profile(
                alignment, geology=geology,
                land_zones=getattr(alignment, "_land_zones", None),
            )
        except Exception as exc:
            self._status_label.setText(f"Vertical chart error: {exc}")

        if cant is not None:
            try:
                self._superelev_widget.update_cant(cant)
            except Exception:
                pass

        cost = getattr(alignment, "_cost", None)
        if cost is not None:
            try:
                self._cost_widget.update_cost(cost)
            except Exception:
                pass

        try:
            self._map_widget.show_track_line(alignment._profile)
        except Exception:
            pass

    # ------------------------------------------------------------------ land acquisition

    def _populate_land_results(self, land, error=None):
        """Update the Land Acquisition section of the results panel."""
        # Clear the per-zone table
        lztl = self._land_zone_table.layout()
        while lztl.count():
            child = lztl.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if land is None:
            self._res_land_corridor.setText("—")
            self._res_land_area.setText("—")
            self._res_land_total.setText("—")
            if error:
                self._land_note_label.setText(f"Land acquisition failed: {error}")
                self._land_note_label.setStyleSheet("color: #ef4444; font-size: 9px;")
            else:
                self._land_note_label.setText(
                    "Enable Land Acquisition in Parameters to include zoning costs."
                )
                self._land_note_label.setStyleSheet("color: #475569; font-size: 9px;")
            return

        if not land.zones:
            self._res_land_corridor.setText(f"{land.corridor_width_m:.0f} m")
            self._res_land_area.setText("0 ha")
            self._res_land_total.setText("$0")
            self._land_note_label.setText(
                "No OSM land-use polygons found along this corridor. "
                "The area may have sparse OSM coverage."
            )
            self._land_note_label.setStyleSheet("color: #f59e0b; font-size: 9px;")
            return

        def _fmt_m(v):
            if v >= 1e9:
                return f"${v/1e9:.2f} B"
            if v >= 1e6:
                return f"${v/1e6:.1f} M"
            return f"${v/1e3:.0f} k"

        self._res_land_corridor.setText(f"{land.corridor_width_m:.0f} m")
        self._res_land_area.setText(f"{land.total_area_m2/10000:.1f} ha")
        self._res_land_total.setText(_fmt_m(land.total_cost))
        self._land_note_label.setText(
            f"Source: {land.data_source}  ·  {land.corridor_width_m:.0f} m corridor"
        )
        self._land_note_label.setStyleSheet("color: #475569; font-size: 9px;")

        # Per-zone rows
        _HDR_SS = "color: #475569; font-size: 9px;"
        _VAL_SS = "color: #94a3b8; font-size: 9px; font-family: monospace;"
        _COST_SS = "color: #22d3ee; font-size: 9px; font-family: monospace;"

        hdr = QLabel("Category                       Area (ha)    $/m²     Cost")
        hdr.setStyleSheet(_HDR_SS)
        lztl.addWidget(hdr)

        for z in land.zones:
            cat  = z.category[:30]
            area = f"{z.area_m2/10000:>8.1f}"
            rate = f"{z.cost_per_m2:>6.0f}"
            cost = _fmt_m(z.subtotal)
            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            lbl = QLabel(f"{cat:<30}  {area} ha  {rate}")
            lbl.setStyleSheet(_VAL_SS)
            val = QLabel(cost)
            val.setStyleSheet(_COST_SS)
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            rl.addWidget(lbl, stretch=1)
            rl.addWidget(val)
            lztl.addWidget(row)

    # ------------------------------------------------------------------ waypoint list

    def _refresh_waypoint_list(self):
        """Rebuild the waypoint rows in the results panel."""
        while self._wp_list_layout.count():
            child = self._wp_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self._waypoints:
            empty = QLabel("No waypoints yet.")
            empty.setStyleSheet("color: #475569; font-size: 10px; padding: 2px 0;")
            self._wp_list_layout.addWidget(empty)
            self._wp_section_title.setText("Waypoints")
            return

        self._wp_section_title.setText(f"Waypoints ({len(self._waypoints)})")
        _DEL_SS = (
            "QPushButton{background:transparent;color:#475569;"
            "border:none;font-size:11px;padding:0 2px;}"
            "QPushButton:hover{color:#ef4444;}"
        )
        for i, wp in enumerate(self._waypoints):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(2, 1, 2, 1)
            rl.setSpacing(4)
            num = QLabel(f"{i+1:>2}.")
            num.setStyleSheet("color:#38bdf8; font-size:10px; min-width:18px;")
            coords = QLabel(f"{wp[0]:.4f},  {wp[1]:.4f}")
            coords.setStyleSheet(
                "color:#94a3b8; font-size:10px; font-family:monospace;"
            )
            del_btn = QPushButton("✕")
            del_btn.setFixedSize(16, 16)
            del_btn.setToolTip(f"Remove waypoint {i+1}")
            del_btn.setStyleSheet(_DEL_SS)
            del_btn.clicked.connect(lambda checked, idx=i: self._delete_waypoint(idx))
            rl.addWidget(num)
            rl.addWidget(coords, stretch=1)
            rl.addWidget(del_btn)
            self._wp_list_layout.addWidget(row)

    def _delete_waypoint(self, index: int):
        self._map_widget.remove_waypoint(index)

    # ------------------------------------------------------------------ save / load route

    def _map_widget_fit(self):
        self._map_widget.fit_to_route()

    def _save_route(self):
        if not self._waypoints:
            QMessageBox.information(self, "Save Route", "No waypoints to save.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Route", "", "Route files (*.json);;All files (*)"
        )
        if not path:
            return
        import json as _json
        with open(path, "w") as f:
            _json.dump({"waypoints": self._waypoints}, f, indent=2)
        self._status_label.setText(f"Route saved — {len(self._waypoints)} waypoints.")

    def _load_route(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Route", "", "Route files (*.json);;All files (*)"
        )
        if not path:
            return
        import json as _json
        try:
            with open(path) as f:
                data = _json.load(f)
            pts = data.get("waypoints", data)   # support bare list too
            if not isinstance(pts, list) or len(pts) < 2:
                raise ValueError("Need at least 2 waypoints.")
            self._map_widget.load_route(pts)
            self._status_label.setText(
                f"Route loaded — {len(pts)} waypoints."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Load Route", f"Could not load route:\n{exc}")

    # ------------------------------------------------------------------ copy results

    def _copy_results(self):
        a = self._alignment
        if a is None:
            QApplication.clipboard().setText("No analysis results yet.")
            return
        cant = getattr(a, "_cant", None)
        cost_s = getattr(a, "_cost", None)
        geology = getattr(a, "_geology", None)

        def _fmt(v):
            return "—" if v is None else str(v)

        lines = [
            "TrackAlong — Analysis Results",
            "=" * 48,
            f"Route length        {a.chainage[-1]/1000:.1f} km"
            f"   ({len(a.chainage):,} stations)",
            f"Max grade           {a.max_grade_pct:.3f} %",
            f"Ruling grade        {a.ruling_grade_pct:.3f} %",
            f"Grade compensation  {'Yes' if a.grade_compensation_applied else 'No'}",
            "",
            "── Earthworks ──────────────────────────────────",
            f"Cut volume          {a.total_cut_m3/1e6:.3f} Mm³",
            f"Fill volume         {a.total_fill_m3/1e6:.3f} Mm³",
            f"Net (cut−fill)      {(a.total_cut_m3-a.total_fill_m3)/1e6:+.3f} Mm³",
        ]

        if cant is not None:
            lines += [
                "",
                "── Horizontal & Speed ──────────────────────────",
                f"Design speed        {cant.design_speed_kph:.0f} km/h",
                f"Min speed on route  {cant.min_speed_kph:.0f} km/h",
                f"Radius violations   {cant.transition_violation_count}",
            ]

        if geology is not None and geology.any_data:
            lbc = geology.length_by_class
            lines += [
                "",
                "── Geology ─────────────────────────────────────",
                f"Hard Rock (A)       {lbc.get('A',0)/1000:.1f} km",
                f"Med Rock  (B)       {lbc.get('B',0)/1000:.1f} km",
                f"Weak Rock (C)       {lbc.get('C',0)/1000:.1f} km",
                f"Soft Gnd  (D)       {lbc.get('D',0)/1000:.1f} km",
            ]

        lines += [
            "",
            "── Structures ──────────────────────────────────",
            f"Tunnels             {a.num_tunnels}  "
            f"({a.total_tunnel_length_m/1000:.2f} km)",
            f"Bridges             {a.num_bridges}  "
            f"({a.total_bridge_length_m/1000:.2f} km)",
        ]

        if cost_s is not None:
            from ..core import costing as _cm
            geo = getattr(a, "_geology", None)
            bands = self._params_panel.get_cost_bands()
            cs = _cm.estimate_costs(a, geo, bands, double_track=False)
            cd = _cm.estimate_costs(a, geo, bands, double_track=True)
            lines += [
                "",
                "── Construction Cost ────────────────────────────",
                f"Single track        ${cs.total/1e6:.0f} M"
                f"  (${cs.total/max(cs.route_length_km,0.001)/1e6:.1f} M/km)",
                f"Double track        ${cd.total/1e6:.0f} M"
                f"  (${cd.total/max(cd.route_length_km,0.001)/1e6:.1f} M/km)",
                f"Earthworks          ${cs.subtotal_earthworks/1e6:.0f} M",
                f"Bridges             ${cs.subtotal_bridges/1e6:.0f} M",
                f"Tunnels             ${cs.subtotal_tunnels/1e6:.0f} M",
                f"Track (single)      ${cs.subtotal_track/1e6:.0f} M",
            ]

        land = getattr(a, "_land_zones", None)
        if land is not None and land.zones:
            def _fmt_m_copy(v):
                if v >= 1e9:
                    return f"${v/1e9:.2f} B"
                if v >= 1e6:
                    return f"${v/1e6:.1f} M"
                return f"${v/1e3:.0f} k"
            lines += [
                "",
                "── Land Acquisition ────────────────────────────",
                f"Corridor width      {land.corridor_width_m:.0f} m",
                f"Total area          {land.total_area_m2/10000:.1f} ha",
                f"Total cost          {_fmt_m_copy(land.total_cost)}",
                "",
                f"  {'Zone code':<20} {'Category':<28} {'Area(ha)':>8}  {'Cost':>10}",
            ]
            for z in land.zones:
                lines.append(
                    f"  {z.zone_code:<20} {z.category:<28} "
                    f"{z.area_m2/10000:>8.1f}  {_fmt_m_copy(z.subtotal):>10}"
                )

        lines.append("")
        lines.append(f"Waypoints: {len(self._waypoints)}")
        for i, wp in enumerate(self._waypoints):
            lines.append(f"  {i+1:>2}. {wp[0]:.5f}, {wp[1]:.5f}")

        QApplication.clipboard().setText("\n".join(lines))
        self._status_label.setText("Results copied to clipboard.")

    # ------------------------------------------------------------------ panel expand/collapse

    def _toggle_params(self):
        self._params_collapsed = not self._params_collapsed
        self._params_panel.setVisible(not self._params_collapsed)
        self._params_toggle_btn.setText(
            "▶  Params" if self._params_collapsed else "◀  Params"
        )

    def _toggle_results(self):
        self._results_collapsed = not self._results_collapsed
        self._results_panel.setVisible(not self._results_collapsed)
        self._results_toggle_btn.setText(
            "Results  ◀" if self._results_collapsed else "Results  ▶"
        )

    def _toggle_center_expand(self, panel: str):
        if self._center_expanded == panel:
            # Restore both panes
            self._center_expanded = None
            self._map_wrap.setVisible(True)
            self._bottom_widget.setVisible(True)
            self._map_expand_btn.setText("⛶")
            self._charts_expand_btn.setText("⛶")
        else:
            self._center_expanded = panel
            if panel == "map":
                self._bottom_widget.setVisible(False)
                self._map_wrap.setVisible(True)
                self._map_expand_btn.setText("⊡")
                self._charts_expand_btn.setText("⛶")
            else:
                self._map_wrap.setVisible(False)
                self._bottom_widget.setVisible(True)
                self._charts_expand_btn.setText("⊡")
                self._map_expand_btn.setText("⛶")

    def _escape_expand(self):
        if self._center_expanded is not None:
            self._toggle_center_expand(self._center_expanded)

    @Slot(str)
    def _on_analysis_error(self, msg):
        self._progress.setVisible(False)
        self._analyse_btn.setEnabled(True)
        self._status_label.setText(f"Error: {msg}")
        QMessageBox.critical(self, "Analysis Error",
                             f"Could not complete analysis:\n\n{msg}")

    # ------------------------------------------------------------------ clear

    def _clear_all(self):
        self._map_widget.clear_route()
        self._waypoints  = []
        self._alignment  = None
        self._refresh_waypoint_list()
        self._profile_widget.clear()
        self._horiz_widget.clear()
        self._superelev_widget.clear()
        self._cost_widget.clear()
        self._analyse_btn.setEnabled(False)
        self._optimise_btn.setEnabled(False)
        self._status_label.setText("Cleared. Plot a route on the map.")

        for attr in (
            "_res_length", "_res_stations", "_res_maxgrade",
            "_res_ruling", "_res_comp",
            "_res_cut", "_res_fill", "_res_net", "_res_ratio",
            "_res_min_radius", "_res_radius_viol",
            "_res_design_spd", "_res_min_spd", "_res_spd_rest",
            "_res_curves", "_res_trans_viol", "_res_rev_viol",
            "_res_twist_viol", "_res_coinc_viol",
            "_res_geo_A", "_res_geo_B", "_res_geo_C", "_res_geo_D",
            "_res_geo_cut", "_res_geo_fill",
            "_res_tun_count", "_res_tun_len", "_res_tun_vol",
            "_res_bri_count", "_res_bri_len", "_res_bri_vol",
            "_res_cost_km", "_res_cost_single", "_res_cost_double",
            "_res_cost_earth", "_res_cost_bridges",
            "_res_cost_tunnels", "_res_cost_track",
            "_res_land_corridor", "_res_land_area", "_res_land_total",
        ):
            getattr(self, attr).setText("—")
            getattr(self, attr).setStyleSheet(
                "color: #e2e8f0; font-size: 12px; font-weight: 600;"
            )

        self._violations_label.setText("—")
        self._tunnel_detail.setText("—")
        self._bridge_detail.setText("—")
        self._geo_risk_label.setText("—")
        self._populate_land_results(None)
