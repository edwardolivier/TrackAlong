export const RAIL_PRESETS = {
  'Standard Freight': {
    max_grade_pct: 1.0, k_crest: 30, k_sag: 50,
    formation_width_m: 8.5, batter_cut: 1.5, batter_fill: 2.0,
    min_radius_m: 400, design_speed_kph: 115, gauge_mm: 1435,
    max_cant_mm: 100, max_cant_deficiency_mm: 75,
  },
  'Regional Passenger': {
    max_grade_pct: 1.5, k_crest: 55, k_sag: 70,
    formation_width_m: 8.5, batter_cut: 1.5, batter_fill: 2.0,
    min_radius_m: 300, design_speed_kph: 160, gauge_mm: 1435,
    max_cant_mm: 110, max_cant_deficiency_mm: 80,
  },
  'High Speed Rail': {
    max_grade_pct: 2.5, k_crest: 200, k_sag: 200,
    formation_width_m: 13.4, batter_cut: 1.5, batter_fill: 2.0,
    min_radius_m: 4000, design_speed_kph: 350, gauge_mm: 1435,
    max_cant_mm: 180, max_cant_deficiency_mm: 100,
  },
  'Light Rail': {
    max_grade_pct: 6.0, k_crest: 10, k_sag: 15,
    formation_width_m: 6.0, batter_cut: 1.5, batter_fill: 2.0,
    min_radius_m: 25, design_speed_kph: 80, gauge_mm: 1435,
    max_cant_mm: 100, max_cant_deficiency_mm: 75,
  },
}

export const DEFAULT_PARAMS = {
  ...RAIL_PRESETS['Standard Freight'],
  k_crest: 30, k_sag: 50,
  cut_trigger_m: 50, fill_trigger_m: 10,
  min_track_elev_m: -1e9,
  cant_gradient_max_mm_per_m: 2.25,
  max_twist_mm_per_3m: 7.0,
  ruling_grade_length_km: 10,
}

export const DEFAULT_CORRIDOR = {
  corridor_km: 30, num_layers: 8, lateral_steps: 7,
  weight_length: 1.0, weight_grade: 5.0,
}
