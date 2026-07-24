"""Radius-of-curvature and cant/speed analysis (deterministic, no network)."""
import numpy as np

from core.cant import compute_radii, analyse_cant, _CANT_FACTOR_DENOM, _STRAIGHT_R
from core.optimizer import GeometryParams


def _params(**kw) -> GeometryParams:
    base = dict(
        max_grade_pct=1.0, k_crest=30.0, k_sag=50.0,
        formation_width_m=8.5, batter_cut=1.5, batter_fill=2.0,
    )
    base.update(kw)
    return GeometryParams(**base)


def _straight_profile(n=201):
    ch = np.linspace(0.0, 2000.0, n)
    lat = np.linspace(-33.0, -33.02, n)
    lng = np.linspace(151.0, 151.02, n)
    elev = np.full(n, 100.0)
    return np.column_stack([ch, lat, lng, elev])


def test_straight_line_has_large_radii():
    radii = compute_radii(_straight_profile())
    # A straight alignment is effectively tangent everywhere (capped at 50 km).
    assert np.all(radii >= _STRAIGHT_R)
    assert radii.max() <= 50_000.0 + 1e-6


def test_circular_arc_recovers_radius():
    # Lay stations on a circle of known radius; the 3-point circumradius should recover it.
    R = 800.0
    lat0 = np.radians(-33.0)
    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * np.cos(lat0)
    theta = np.linspace(0.0, 0.6, 200)
    x = R * np.cos(theta)
    y = R * np.sin(theta)
    lat = -33.0 + y / m_per_deg_lat
    lng = 151.0 + x / m_per_deg_lng
    ch = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    profile = np.column_stack([ch, lat, lng, np.full_like(ch, 100.0)])
    radii = compute_radii(profile)
    interior = radii[10:-10]
    assert np.isclose(np.median(interior), R, rtol=0.05)


def test_analyse_cant_straight_is_uncanted():
    profile = _straight_profile()
    radii = compute_radii(profile)
    ca = analyse_cant(profile[:, 0], radii, _params(design_speed_kph=120.0))
    assert np.allclose(ca.equilibrium_cant, 0.0)
    assert ca.min_speed_kph == 120.0          # no restriction on tangent track
    assert ca.curves == []


def test_equilibrium_cant_formula():
    # One tight curve: eq cant = gauge * V^2 / 127.06 / R
    R = 500.0
    n = 101
    radii = np.full(n, R)
    ch = np.linspace(0.0, 1000.0, n)
    p = _params(design_speed_kph=100.0, gauge_mm=1435.0)
    ca = analyse_cant(ch, radii, p)
    expected = 1435.0 * (100.0 ** 2) / _CANT_FACTOR_DENOM / R
    assert np.isclose(ca.equilibrium_cant.max(), expected, rtol=1e-6)
