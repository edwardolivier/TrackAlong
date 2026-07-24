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

export const DEFAULT_COST_BANDS = {
  // Cut $/m³ by geology
  cut_A: 90.0, cut_B: 55.0, cut_C: 32.0, cut_D: 20.0, cut_unknown: 40.0,
  // Fill $/m³ by geology
  fill_A: 40.0, fill_B: 30.0, fill_C: 25.0, fill_D: 20.0, fill_unknown: 28.0,
  // Cut depth multipliers
  cut_band1_m: 5.0, cut_band2_m: 15.0, cut_mult_medium: 1.30, cut_mult_deep: 1.60,
  // Fill height multipliers
  fill_band1_m: 3.0, fill_band2_m: 8.0, fill_mult_medium: 1.20, fill_mult_high: 1.40,
  // Bridge $/m by height
  bridge_band1_m: 5.0, bridge_band2_m: 15.0,
  bridge_rate_low: 30000.0, bridge_rate_medium: 65000.0, bridge_rate_high: 120000.0,
  // Tunnel $/m by geology
  tunnel_A: 45000.0, tunnel_B: 75000.0, tunnel_C: 100000.0, tunnel_D: 130000.0, tunnel_unknown: 90000.0,
  // Track $/m (single track)
  track_rail: 150.0, track_sleeper: 280.0, track_ballast: 140.0,
  track_capping: 75.0, track_fastenings: 80.0, track_drainage: 60.0, track_formation: 115.0,
  double_track_factor: 1.8,
  // Rail systems $/m
  signalling_per_m: 250.0, comms_per_m: 80.0, power_per_m: 120.0,
  // Other
  contingency_pct: 20.0, formation_width_m: 5.5,
}

export const DEFAULT_CORRIDOR = {
  corridor_km: 30, num_layers: 8, lateral_steps: 7,
  weight_length: 1.0, weight_grade: 5.0,
}

// Land acquisition — 8 cost categories (AUD/m²), mirrors core land_zoning defaults.
export const LAND_CATEGORIES = [
  'Crown / Conservation', 'Rural / Agricultural',
  'Residential (low density)', 'Residential (med/high density)',
  'Commercial', 'Industrial', 'Infrastructure', 'Other',
]

export const DEFAULT_LAND = {
  include: true,
  corridor_m: 30,
  category_costs: {
    'Crown / Conservation': 0.0,
    'Rural / Agricultural': 3.0,
    'Residential (low density)': 200.0,
    'Residential (med/high density)': 400.0,
    'Commercial': 350.0,
    'Industrial': 180.0,
    'Infrastructure': 50.0,
    'Other': 30.0,
  },
}

// Route optimiser presets (mirror core route_optimizer INTENSITY / OBJECTIVE tables).
export const OPTIMISER_INTENSITY = {
  Low:    { num_layers: 5,  lateral_steps: 5 },
  Medium: { num_layers: 8,  lateral_steps: 7 },
  High:   { num_layers: 12, lateral_steps: 9 },
}

export const OPTIMISER_OBJECTIVE = {
  'Shortest path':      { weight_length: 1.0, weight_grade: 0.3 },
  'Balanced':           { weight_length: 1.0, weight_grade: 5.0 },
  'Minimise earthwork': { weight_length: 0.4, weight_grade: 15.0 },
}
