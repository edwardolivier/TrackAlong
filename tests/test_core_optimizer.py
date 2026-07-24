"""Vertical alignment optimiser + earthwork volume helpers (deterministic, no network)."""
import numpy as np

from core.optimizer import (
    GeometryParams,
    optimise,
    _cross_section_area,
    _prismatic_volumes,
    _lp_grade_line,
    _ruling_grade,
)


def _params(**kw) -> GeometryParams:
    base = dict(
        max_grade_pct=1.0, k_crest=30.0, k_sag=50.0,
        formation_width_m=8.5, batter_cut=1.5, batter_fill=2.0,
    )
    base.update(kw)
    return GeometryParams(**base)


def test_cross_section_area():
    # width*depth + batter*depth^2  = 8.5*2 + 1.5*4 = 23
    assert _cross_section_area(2.0, 8.5, 1.5) == 23.0
    assert _cross_section_area(0.0, 8.5, 1.5) == 0.0
    assert _cross_section_area(-3.0, 8.5, 1.5) == 0.0  # negative depth -> no area


def test_prismatic_volumes():
    ch = np.array([0.0, 10.0])
    depth = np.array([2.0, 2.0])
    vols = _prismatic_volumes(depth, ch, width=8.5, batter=1.5)
    # single 10 m interval, constant 23 m^2 area -> 230 m^3
    assert np.isclose(vols.sum(), 230.0)


def test_lp_grade_line_follows_gentle_ramp():
    # Ground rises 0.5%/m, well within the 1% limit -> LP track should hug the ground
    # (near-zero cut/fill), not flatten it.
    ch = np.linspace(0.0, 2000.0, 201)
    ground = 100.0 + 0.005 * ch
    track = _lp_grade_line(ground, ch, max_grade_pct=1.0)
    assert np.allclose(track, ground, atol=1.0)


def test_ruling_grade_matches_uniform_grade():
    ch = np.linspace(0.0, 20000.0, 2001)
    grade = np.full_like(ch, 0.8)  # uniform 0.8%
    assert np.isclose(_ruling_grade(grade, ch, window_km=10.0), 0.8, atol=1e-6)


def test_optimise_smoke(synthetic_profile):
    al = optimise(synthetic_profile, _params())
    n = len(synthetic_profile)
    # Output arrays are station-aligned
    assert len(al.track) == n == len(al.cut) == len(al.fill) == len(al.grade)
    # Physical sanity
    assert al.total_cut_m3 >= 0.0
    assert al.total_fill_m3 >= 0.0
    assert np.all(al.cut >= 0.0) and np.all(al.fill >= 0.0)
    # A hill means at least some cut is required somewhere
    assert al.cut.max() > 0.0
    # Grade respects the limit (with the optimiser's 2% tolerance band)
    assert al.max_grade_pct <= 1.0 * 1.02 + 1e-6


def test_min_track_elevation_constraint(synthetic_profile):
    al = optimise(synthetic_profile, _params(min_track_elev_m=130.0))
    assert al.track.min() >= 130.0 - 1e-6
