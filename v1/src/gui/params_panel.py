"""
Left-side parameters panel: railway type selector + editable geometry fields.
"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QDoubleSpinBox, QGroupBox, QFormLayout, QFrame, QPushButton,
    QSizePolicy, QCheckBox, QScrollArea,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

RAIL_TYPES_PATH = Path(__file__).parent.parent.parent / "config" / "rail_types.json"


class ParamsPanel(QWidget):
    params_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)

        with open(RAIL_TYPES_PATH) as f:
            self._rail_types = json.load(f)

        self._building = True
        self._build_ui()
        self._building = False
        self._load_preset("heavy_freight")

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # Wrap everything in a scroll area so the panel isn't truncated
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: #0f172a; }"
            "QScrollBar:vertical { background: #1e293b; width: 6px; }"
            "QScrollBar::handle:vertical { background: #334155; border-radius: 3px; }"
        )

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("TrackAlong")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #38bdf8;")
        layout.addWidget(title)

        sub = QLabel("Railway Alignment Analyser")
        sub.setStyleSheet("color: #64748b; font-size: 11px;")
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #334155;")
        layout.addWidget(sep)

        # ── Railway type ──────────────────────────────────────────────────────
        grp_type = QGroupBox("Railway Type")
        grp_type.setStyleSheet(self._grp_style())
        type_layout = QVBoxLayout(grp_type)
        type_layout.setSpacing(4)

        self._combo = QComboBox()
        self._combo.setStyleSheet(self._combo_style())
        for key, cfg in self._rail_types.items():
            self._combo.addItem(cfg["name"], key)
        self._combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self._combo)

        self._desc_label = QLabel("")
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet("color: #64748b; font-size: 10px;")
        type_layout.addWidget(self._desc_label)
        layout.addWidget(grp_type)

        # ── Geometry constraints ──────────────────────────────────────────────
        grp_geom = QGroupBox("Geometry Constraints")
        grp_geom.setStyleSheet(self._grp_style())
        form = QFormLayout(grp_geom)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(6)

        def spin(lo, hi, dec, suffix=""):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(dec)
            s.setSuffix(suffix)
            s.setStyleSheet(self._spin_style())
            s.valueChanged.connect(self._on_param_changed)
            return s

        self._spin_grade  = spin(0.05, 10.0,   2, " %")
        self._spin_radius = spin(25,   50000,   0, " m")
        self._spin_k_crest = spin(10,  100000,  0)
        self._spin_k_sag   = spin(10,  100000,  0)
        self._spin_width   = spin(3.0, 20.0,    1, " m")
        self._spin_batter_cut  = spin(0.1, 5.0, 1, " H:1V")
        self._spin_batter_fill = spin(0.1, 5.0, 1, " H:1V")

        form.addRow("Max grade:",       self._spin_grade)
        form.addRow("Min radius:",      self._spin_radius)
        form.addRow("K-value crest:",   self._spin_k_crest)
        form.addRow("K-value sag:",     self._spin_k_sag)
        form.addRow("Formation width:", self._spin_width)
        form.addRow("Cut batter:",      self._spin_batter_cut)
        form.addRow("Fill batter:",     self._spin_batter_fill)
        layout.addWidget(grp_geom)

        # ── Speed & cant ──────────────────────────────────────────────────────
        grp_cant = QGroupBox("Speed & Cant (Superelevation)")
        grp_cant.setStyleSheet(self._grp_style())
        cant_form = QFormLayout(grp_cant)
        cant_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        cant_form.setSpacing(6)

        self._spin_speed  = spin(20, 600, 0, " km/h")
        self._spin_speed.setToolTip("Design speed for cant and transition calculations.")

        self._combo_gauge = QComboBox()
        self._combo_gauge.setStyleSheet(self._combo_style())
        self._combo_gauge.addItem("Standard  1435 mm", 1435)
        self._combo_gauge.addItem("Narrow    1067 mm", 1067)
        self._combo_gauge.addItem("Broad     1600 mm", 1600)
        self._combo_gauge.currentIndexChanged.connect(self._on_param_changed)

        self._spin_max_cant = spin(50, 300, 0, " mm")
        self._spin_max_cant.setToolTip(
            "Maximum cant (superelevation) allowed on this route.\n"
            "Typical: 100 mm freight, 150 mm passenger, 180 mm HSR."
        )
        self._spin_cant_def = spin(20, 200, 0, " mm")
        self._spin_cant_def.setToolTip(
            "Maximum cant deficiency (unbalanced centrifugal force).\n"
            "Typical: 75 mm freight, 100 mm passenger, 130 mm HSR."
        )
        self._spin_cant_grad = spin(0.5, 10.0, 2, " mm/m")
        self._spin_cant_grad.setToolTip(
            "Maximum rate of cant application along the transition.\n"
            "ARTC standard: 2.25 mm/m.  Governs minimum transition length."
        )
        self._spin_max_twist = spin(1.0, 20.0, 1, " mm/3m")
        self._spin_max_twist.setToolTip(
            "Track twist limit — rate of change of cross-level over 3 m.\n"
            "ARTC: 7 mm/3m freight, 5 mm/3m passenger, 3 mm/3m HSR."
        )

        cant_form.addRow("Design speed:",    self._spin_speed)
        cant_form.addRow("Track gauge:",     self._combo_gauge)
        cant_form.addRow("Max cant:",        self._spin_max_cant)
        cant_form.addRow("Cant deficiency:", self._spin_cant_def)
        cant_form.addRow("Cant gradient:",   self._spin_cant_grad)
        cant_form.addRow("Max twist:",       self._spin_max_twist)
        layout.addWidget(grp_cant)

        # ── Structure triggers ────────────────────────────────────────────────
        grp_struct = QGroupBox("Structure Triggers")
        grp_struct.setStyleSheet(self._grp_style())
        struct_form = QFormLayout(grp_struct)
        struct_form.setSpacing(6)

        self._spin_cut_trigger = spin(5.0, 500.0, 0, " m")
        self._spin_cut_trigger.setValue(50.0)
        self._spin_cut_trigger.setToolTip("Cut deeper than this → Tunnel (default 50 m)")
        self._spin_fill_trigger = spin(1.0, 100.0, 0, " m")
        self._spin_fill_trigger.setValue(10.0)
        self._spin_fill_trigger.setToolTip("Fill higher than this → Bridge (default 10 m)")

        struct_form.addRow("Tunnel if cut >:", self._spin_cut_trigger)
        struct_form.addRow("Bridge if fill >:", self._spin_fill_trigger)
        layout.addWidget(grp_struct)

        # ── Analysis settings ─────────────────────────────────────────────────
        grp_int = QGroupBox("Analysis Settings")
        grp_int.setStyleSheet(self._grp_style())
        int_form = QFormLayout(grp_int)
        int_form.setSpacing(6)

        self._spin_interval = spin(5, 100, 0, " m")
        self._spin_interval.setValue(10)
        int_form.addRow("Station interval:", self._spin_interval)

        self._spin_ruling_km = spin(1.0, 50.0, 0, " km")
        self._spin_ruling_km.setValue(10.0)
        self._spin_ruling_km.setToolTip(
            "Length over which ruling (average) grade is measured.\n"
            "ARTC freight: 10 km.  Passenger: 5 km.  HSR: 3 km."
        )
        int_form.addRow("Ruling grade over:", self._spin_ruling_km)

        # Min track elevation
        elev_row = QWidget()
        elev_layout = QHBoxLayout(elev_row)
        elev_layout.setContentsMargins(0, 0, 0, 0)
        elev_layout.setSpacing(4)

        self._chk_min_elev = QCheckBox()
        self._chk_min_elev.setChecked(False)
        self._chk_min_elev.setToolTip(
            "Enforce a minimum track elevation (e.g. above sea level / flood datum)."
        )
        self._chk_min_elev.setStyleSheet("QCheckBox { color: #94a3b8; }")
        self._chk_min_elev.toggled.connect(self._on_min_elev_toggled)
        elev_layout.addWidget(self._chk_min_elev)

        self._spin_min_elev = QDoubleSpinBox()
        self._spin_min_elev.setRange(-500.0, 8000.0)
        self._spin_min_elev.setDecimals(0)
        self._spin_min_elev.setSuffix(" m")
        self._spin_min_elev.setValue(0.0)
        self._spin_min_elev.setEnabled(False)
        self._spin_min_elev.setStyleSheet(self._spin_style())
        self._spin_min_elev.valueChanged.connect(self._on_param_changed)
        elev_layout.addWidget(self._spin_min_elev, stretch=1)

        int_form.addRow("Min track elev:", elev_row)
        layout.addWidget(grp_int)

        # ── Route optimiser ───────────────────────────────────────────────────
        grp_route = QGroupBox("Route Optimiser")
        grp_route.setStyleSheet(self._grp_style())
        route_form = QFormLayout(grp_route)
        route_form.setSpacing(6)

        self._spin_corridor = spin(5.0, 200.0, 0, " km")
        self._spin_corridor.setValue(30.0)
        self._spin_corridor.setToolTip(
            "Half-width of the lateral search corridor.\n"
            "Larger values explore more detour options."
        )

        self._combo_intensity = QComboBox()
        self._combo_intensity.setStyleSheet(self._combo_style())
        self._combo_intensity.addItems(["Low (fast)", "Medium", "High (thorough)"])
        self._combo_intensity.setCurrentIndex(1)

        self._combo_objective = QComboBox()
        self._combo_objective.setStyleSheet(self._combo_style())
        self._combo_objective.addItems(
            ["Shortest path", "Balanced", "Minimise earthwork"]
        )
        self._combo_objective.setCurrentIndex(1)

        route_form.addRow("Corridor width:", self._spin_corridor)
        route_form.addRow("Intensity:",      self._combo_intensity)
        route_form.addRow("Objective:",      self._combo_objective)
        layout.addWidget(grp_route)

        # ── Construction Costs ────────────────────────────────────────────────
        layout.addWidget(self._build_cost_group())

        # ── Land Acquisition ──────────────────────────────────────────────────
        layout.addWidget(self._build_land_group())

        layout.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------ helpers

    def _grp_style(self):
        return """
            QGroupBox {
                color: #94a3b8; font-size: 11px; font-weight: 600;
                border: 1px solid #334155; border-radius: 6px;
                margin-top: 6px; padding-top: 8px;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """

    def _combo_style(self):
        return """
            QComboBox {
                background: #1e293b; color: #e2e8f0;
                border: 1px solid #334155; border-radius: 4px;
                padding: 4px 6px; font-size: 12px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1e293b; color: #e2e8f0;
                selection-background-color: #0ea5e9;
            }
        """

    def _spin_style(self):
        return """
            QDoubleSpinBox {
                background: #1e293b; color: #e2e8f0;
                border: 1px solid #334155; border-radius: 4px;
                padding: 2px 4px; font-size: 11px;
            }
        """

    # ------------------------------------------------------------------ slots

    def _on_type_changed(self, index):
        key = self._combo.itemData(index)
        self._load_preset(key)

    def _load_preset(self, key):
        self._building = True
        cfg = self._rail_types[key]
        self._desc_label.setText(cfg.get("description", ""))
        self._spin_grade.setValue(cfg["max_grade_pct"])
        self._spin_radius.setValue(cfg["min_radius_m"])
        self._spin_k_crest.setValue(cfg["k_crest"])
        self._spin_k_sag.setValue(cfg["k_sag"])
        self._spin_width.setValue(cfg["formation_width_m"])
        self._spin_batter_cut.setValue(cfg["batter_cut"])
        self._spin_batter_fill.setValue(cfg["batter_fill"])
        # Speed & cant
        self._spin_speed.setValue(cfg.get("design_speed_kmh", 115))
        gauge = cfg.get("gauge_mm", 1435)
        for i in range(self._combo_gauge.count()):
            if self._combo_gauge.itemData(i) == gauge:
                self._combo_gauge.setCurrentIndex(i)
                break
        self._spin_max_cant.setValue(cfg.get("max_cant_mm", 100))
        self._spin_cant_def.setValue(cfg.get("max_cant_deficiency_mm", 75))
        self._spin_cant_grad.setValue(cfg.get("cant_gradient_max_mm_per_m", 2.25))
        self._spin_max_twist.setValue(cfg.get("max_twist_mm_per_3m", 7.0))
        self._spin_ruling_km.setValue(cfg.get("ruling_grade_length_km", 10.0))
        self._building = False
        self.params_changed.emit(self.get_params())

    def _on_min_elev_toggled(self, checked):
        self._spin_min_elev.setEnabled(checked)
        if not self._building:
            self.params_changed.emit(self.get_params())

    def _on_param_changed(self):
        if not self._building:
            self.params_changed.emit(self.get_params())

    # ------------------------------------------------------------------ cost group

    def _build_cost_group(self) -> QGroupBox:
        from ..core.costing import CostBands
        _d = CostBands()   # defaults

        grp = QGroupBox("Construction Costs")
        grp.setStyleSheet(self._grp_style())
        form = QFormLayout(grp)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(5)

        def ispin(lo, hi, val, suffix="", step=1):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(0)
            s.setSingleStep(step)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setStyleSheet(self._spin_style())
            s.valueChanged.connect(self._on_param_changed)
            return s

        def fspin(lo, hi, val, dec=2, suffix=""):
            s = QDoubleSpinBox()
            s.setRange(lo, hi)
            s.setDecimals(dec)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setStyleSheet(self._spin_style())
            s.valueChanged.connect(self._on_param_changed)
            return s

        # Track option
        self._combo_track = QComboBox()
        self._combo_track.setStyleSheet(self._combo_style())
        self._combo_track.addItem("Single track", False)
        self._combo_track.addItem("Double track", True)
        self._combo_track.currentIndexChanged.connect(self._on_param_changed)
        form.addRow("Track option:", self._combo_track)

        self._spin_contingency = ispin(0, 100, _d.contingency_pct, " %")
        form.addRow("Contingency:", self._spin_contingency)

        def _sep(text):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #475569; font-size: 10px; margin-top: 4px;")
            form.addRow(lbl)

        # Earthworks cut
        _sep("── Cut rates ($/m³) by geology ──")
        self._cc_cut_A = ispin(10, 500, _d.cut_A, step=5)
        self._cc_cut_B = ispin(10, 500, _d.cut_B, step=5)
        self._cc_cut_C = ispin(10, 500, _d.cut_C, step=5)
        self._cc_cut_D = ispin(10, 500, _d.cut_D, step=5)
        form.addRow("Cut Hard Rock A:", self._cc_cut_A)
        form.addRow("Cut Med Rock  B:", self._cc_cut_B)
        form.addRow("Cut Weak Rock C:", self._cc_cut_C)
        form.addRow("Cut Soft Gnd  D:", self._cc_cut_D)

        # Cut height multipliers
        _sep("── Cut depth multipliers ──")
        self._cc_cut_m1 = fspin(1.0, 3.0, _d.cut_mult_medium, 2, " ×")
        self._cc_cut_m1.setToolTip("Multiplier for cut 5–15 m deep")
        self._cc_cut_m2 = fspin(1.0, 4.0, _d.cut_mult_deep, 2, " ×")
        self._cc_cut_m2.setToolTip("Multiplier for cut > 15 m deep")
        form.addRow("5–15 m mult:", self._cc_cut_m1)
        form.addRow(">15 m mult:",  self._cc_cut_m2)

        # Earthworks fill
        _sep("── Fill rates ($/m³) by geology ──")
        self._cc_fill_A = ispin(10, 300, _d.fill_A, step=5)
        self._cc_fill_B = ispin(10, 300, _d.fill_B, step=5)
        self._cc_fill_C = ispin(10, 300, _d.fill_C, step=5)
        self._cc_fill_D = ispin(10, 300, _d.fill_D, step=5)
        form.addRow("Fill Hard Rock A:", self._cc_fill_A)
        form.addRow("Fill Med Rock  B:", self._cc_fill_B)
        form.addRow("Fill Weak Rock C:", self._cc_fill_C)
        form.addRow("Fill Soft Gnd  D:", self._cc_fill_D)

        # Fill height multipliers
        _sep("── Fill height multipliers ──")
        self._cc_fill_m1 = fspin(1.0, 3.0, _d.fill_mult_medium, 2, " ×")
        self._cc_fill_m1.setToolTip("Multiplier for fill 3–8 m high")
        self._cc_fill_m2 = fspin(1.0, 4.0, _d.fill_mult_high, 2, " ×")
        self._cc_fill_m2.setToolTip("Multiplier for fill > 8 m high")
        form.addRow("3–8 m mult:", self._cc_fill_m1)
        form.addRow(">8 m mult:",  self._cc_fill_m2)

        # Bridge rates
        _sep("── Bridge rates ($/m) by height ──")
        self._cc_br_low  = ispin(5000, 500000, _d.bridge_rate_low,  step=5000)
        self._cc_br_med  = ispin(5000, 500000, _d.bridge_rate_medium, step=5000)
        self._cc_br_high = ispin(5000, 500000, _d.bridge_rate_high, step=5000)
        self._cc_br_low.setToolTip("Bridge < 5 m high ($/m)")
        self._cc_br_med.setToolTip("Bridge 5–15 m high ($/m)")
        self._cc_br_high.setToolTip("Bridge > 15 m high ($/m)")
        form.addRow("Bridge <5 m:",    self._cc_br_low)
        form.addRow("Bridge 5–15 m:",  self._cc_br_med)
        form.addRow("Bridge >15 m:",   self._cc_br_high)

        # Tunnel rates
        _sep("── Tunnel rates ($/m) by geology ──")
        self._cc_tun_A = ispin(10000, 500000, _d.tunnel_A, step=5000)
        self._cc_tun_B = ispin(10000, 500000, _d.tunnel_B, step=5000)
        self._cc_tun_C = ispin(10000, 500000, _d.tunnel_C, step=5000)
        self._cc_tun_D = ispin(10000, 500000, _d.tunnel_D, step=5000)
        form.addRow("Tunnel Hard A:", self._cc_tun_A)
        form.addRow("Tunnel Med  B:", self._cc_tun_B)
        form.addRow("Tunnel Weak C:", self._cc_tun_C)
        form.addRow("Tunnel Soft D:", self._cc_tun_D)

        # Track component rates
        _sep("── Track rates ($/m, single track) ──")
        self._cc_t_rail   = ispin(10, 2000, _d.track_rail)
        self._cc_t_sleep  = ispin(10, 2000, _d.track_sleeper)
        self._cc_t_bast   = ispin(10, 2000, _d.track_ballast)
        self._cc_t_cap    = ispin(10, 2000, _d.track_capping)
        self._cc_t_fast   = ispin(10, 2000, _d.track_fastenings)
        self._cc_t_drain  = ispin(10, 2000, _d.track_drainage)
        self._cc_t_form   = ispin(10, 2000, _d.track_formation)
        self._cc_t_dbl    = fspin(1.0, 3.0, _d.double_track_factor, 2, " ×")
        form.addRow("Rail 60 kg/m:",    self._cc_t_rail)
        form.addRow("Sleepers:",        self._cc_t_sleep)
        form.addRow("Ballast:",         self._cc_t_bast)
        form.addRow("Capping:",         self._cc_t_cap)
        form.addRow("Fastenings:",      self._cc_t_fast)
        form.addRow("Drainage:",        self._cc_t_drain)
        form.addRow("Formation:",       self._cc_t_form)
        form.addRow("Double factor:",   self._cc_t_dbl)

        return grp

    # ------------------------------------------------------------------ land acquisition group

    def _build_land_group(self) -> QGroupBox:
        from ..core.land_zoning import DEFAULT_CATEGORY_COSTS

        grp = QGroupBox("Land Acquisition")
        grp.setStyleSheet(self._grp_style())
        outer = QVBoxLayout(grp)
        outer.setSpacing(6)

        # ── Enable checkbox ───────────────────────────────────────────────────
        self._chk_land = QCheckBox("Enable land acquisition costing")
        self._chk_land.setChecked(False)
        self._chk_land.setStyleSheet("QCheckBox { color: #94a3b8; font-size: 11px; }")
        self._chk_land.toggled.connect(self._on_land_toggled)
        outer.addWidget(self._chk_land)

        src_lbl = QLabel("Data: OpenStreetMap (fetched automatically)")
        src_lbl.setStyleSheet("color: #475569; font-size: 9px; font-style: italic;")
        outer.addWidget(src_lbl)

        # ── Content widget (hidden when disabled) ─────────────────────────────
        self._land_content = QWidget()
        lc = QVBoxLayout(self._land_content)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(6)
        self._land_content.setEnabled(False)

        # Corridor width
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(5)

        self._spin_land_corridor = QDoubleSpinBox()
        self._spin_land_corridor.setRange(5.0, 500.0)
        self._spin_land_corridor.setDecimals(0)
        self._spin_land_corridor.setValue(30.0)
        self._spin_land_corridor.setSuffix(" m")
        self._spin_land_corridor.setStyleSheet(self._spin_style())
        self._spin_land_corridor.setToolTip(
            "Total width of the land acquisition corridor centred on the track centreline."
        )
        form.addRow("Corridor width:", self._spin_land_corridor)
        lc.addLayout(form)

        # Category cost rates
        sep = QLabel("── Cost rates (AUD / m²) by category ──")
        sep.setStyleSheet("color: #475569; font-size: 10px; margin-top: 4px;")
        lc.addWidget(sep)

        self._land_cost_spins: dict[str, QDoubleSpinBox] = {}
        cost_form = QFormLayout()
        cost_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        cost_form.setSpacing(4)

        for category, default_rate in DEFAULT_CATEGORY_COSTS.items():
            s = QDoubleSpinBox()
            s.setRange(0.0, 100000.0)
            s.setDecimals(2)
            s.setValue(default_rate)
            s.setSuffix(" $/m²")
            s.setStyleSheet(self._spin_style())
            self._land_cost_spins[category] = s
            short = category[:22]
            cost_form.addRow(f"{short}:", s)

        lc.addLayout(cost_form)
        outer.addWidget(self._land_content)
        return grp

    def _on_land_toggled(self, checked: bool):
        self._land_content.setEnabled(checked)

    def get_land_params(self) -> dict:
        """Return land acquisition settings for the analysis worker."""
        category_costs = {
            cat: spin.value()
            for cat, spin in self._land_cost_spins.items()
        }
        return {
            "enabled":        self._chk_land.isChecked(),
            "corridor_m":     self._spin_land_corridor.value(),
            "category_costs": category_costs,
        }

    def get_cost_bands(self):
        from ..core.costing import CostBands
        return CostBands(
            cut_A=self._cc_cut_A.value(),
            cut_B=self._cc_cut_B.value(),
            cut_C=self._cc_cut_C.value(),
            cut_D=self._cc_cut_D.value(),
            cut_mult_medium=self._cc_cut_m1.value(),
            cut_mult_deep=self._cc_cut_m2.value(),
            fill_A=self._cc_fill_A.value(),
            fill_B=self._cc_fill_B.value(),
            fill_C=self._cc_fill_C.value(),
            fill_D=self._cc_fill_D.value(),
            fill_mult_medium=self._cc_fill_m1.value(),
            fill_mult_high=self._cc_fill_m2.value(),
            bridge_rate_low=self._cc_br_low.value(),
            bridge_rate_medium=self._cc_br_med.value(),
            bridge_rate_high=self._cc_br_high.value(),
            tunnel_A=self._cc_tun_A.value(),
            tunnel_B=self._cc_tun_B.value(),
            tunnel_C=self._cc_tun_C.value(),
            tunnel_D=self._cc_tun_D.value(),
            track_rail=self._cc_t_rail.value(),
            track_sleeper=self._cc_t_sleep.value(),
            track_ballast=self._cc_t_bast.value(),
            track_capping=self._cc_t_cap.value(),
            track_fastenings=self._cc_t_fast.value(),
            track_drainage=self._cc_t_drain.value(),
            track_formation=self._cc_t_form.value(),
            double_track_factor=self._cc_t_dbl.value(),
            contingency_pct=self._spin_contingency.value(),
            formation_width_m=self.get_params()["formation_width_m"],
        )

    def is_double_track(self) -> bool:
        return bool(self._combo_track.currentData())

    def get_route_params(self):
        from ..core.route_optimizer import INTENSITY, OBJECTIVE, CorridorParams
        num_layers, lateral_steps = INTENSITY.get(
            self._combo_intensity.currentText(), (8, 7)
        )
        weight_length, weight_grade = OBJECTIVE.get(
            self._combo_objective.currentText(), (1.0, 5.0)
        )
        return CorridorParams(
            corridor_km=self._spin_corridor.value(),
            num_layers=num_layers,
            lateral_steps=lateral_steps,
            weight_length=weight_length,
            weight_grade=weight_grade,
        )

    def get_params(self):
        return {
            "max_grade_pct":            self._spin_grade.value(),
            "min_radius_m":             self._spin_radius.value(),
            "k_crest":                  self._spin_k_crest.value(),
            "k_sag":                    self._spin_k_sag.value(),
            "formation_width_m":        self._spin_width.value(),
            "batter_cut":               self._spin_batter_cut.value(),
            "batter_fill":              self._spin_batter_fill.value(),
            "cut_trigger_m":            self._spin_cut_trigger.value(),
            "fill_trigger_m":           self._spin_fill_trigger.value(),
            "interval_m":               self._spin_interval.value(),
            "min_track_elev_m": (
                self._spin_min_elev.value()
                if self._chk_min_elev.isChecked() else -1e9
            ),
            "design_speed_kph":         self._spin_speed.value(),
            "gauge_mm":                 self._combo_gauge.currentData(),
            "max_cant_mm":              self._spin_max_cant.value(),
            "max_cant_deficiency_mm":   self._spin_cant_def.value(),
            "cant_gradient_max_mm_per_m": self._spin_cant_grad.value(),
            "max_twist_mm_per_3m":      self._spin_max_twist.value(),
            "ruling_grade_length_km":   self._spin_ruling_km.value(),
        }
