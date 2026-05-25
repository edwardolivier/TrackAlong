from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional


class GeometryParamsModel(BaseModel):
    max_grade_pct: float = 1.0
    k_crest: float = 30.0
    k_sag: float = 50.0
    formation_width_m: float = 8.5
    batter_cut: float = 1.5
    batter_fill: float = 2.0
    cut_trigger_m: float = 50.0
    fill_trigger_m: float = 10.0
    min_track_elev_m: float = -1e9
    design_speed_kph: float = 115.0
    gauge_mm: float = 1435.0
    max_cant_mm: float = 100.0
    max_cant_deficiency_mm: float = 75.0
    cant_gradient_max_mm_per_m: float = 2.25
    max_twist_mm_per_3m: float = 7.0
    ruling_grade_length_km: float = 10.0
    min_radius_m: float = 400.0


class CostBandsModel(BaseModel):
    cut_A: float = 90.0
    cut_B: float = 55.0
    cut_C: float = 32.0
    cut_D: float = 20.0
    cut_unknown: float = 40.0
    fill_A: float = 40.0
    fill_B: float = 30.0
    fill_C: float = 25.0
    fill_D: float = 20.0
    fill_unknown: float = 28.0
    cut_band1_m: float = 5.0
    cut_band2_m: float = 15.0
    cut_mult_medium: float = 1.30
    cut_mult_deep: float = 1.60
    fill_band1_m: float = 3.0
    fill_band2_m: float = 8.0
    fill_mult_medium: float = 1.20
    fill_mult_high: float = 1.40
    bridge_band1_m: float = 5.0
    bridge_band2_m: float = 15.0
    bridge_rate_low: float = 30_000.0
    bridge_rate_medium: float = 65_000.0
    bridge_rate_high: float = 120_000.0
    tunnel_A: float = 45_000.0
    tunnel_B: float = 75_000.0
    tunnel_C: float = 100_000.0
    tunnel_D: float = 130_000.0
    tunnel_unknown: float = 90_000.0
    track_rail: float = 150.0
    track_sleeper: float = 280.0
    track_ballast: float = 140.0
    track_capping: float = 75.0
    track_fastenings: float = 80.0
    track_drainage: float = 60.0
    track_formation: float = 115.0
    double_track_factor: float = 1.8
    contingency_pct: float = 20.0
    formation_width_m: float = 5.5


class CorridorParamsModel(BaseModel):
    corridor_km: float = 30.0
    num_layers: int = 8
    lateral_steps: int = 7
    weight_length: float = 1.0
    weight_grade: float = 5.0


class AnalyseRequest(BaseModel):
    waypoints: List[List[float]]
    params: GeometryParamsModel = Field(default_factory=GeometryParamsModel)
    cost_bands: CostBandsModel = Field(default_factory=CostBandsModel)
    double_track: bool = False
    corridor_m: float = 30.0
    land_category_costs: Optional[dict] = None
    include_geology: bool = True
    include_land_zones: bool = True


class OptimiseRouteRequest(BaseModel):
    waypoints: List[List[float]]
    params: GeometryParamsModel = Field(default_factory=GeometryParamsModel)
    corridor: CorridorParamsModel = Field(default_factory=CorridorParamsModel)
