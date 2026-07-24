"""Construction cost estimator (deterministic, no network)."""
import numpy as np

from core.costing import estimate_costs, CostBands
from core.optimizer import GeometryParams, optimise


def _params():
    return GeometryParams(
        max_grade_pct=1.0, k_crest=30.0, k_sag=50.0,
        formation_width_m=8.5, batter_cut=1.5, batter_fill=2.0,
    )


def test_estimate_costs_smoke(synthetic_profile):
    al = optimise(synthetic_profile, _params())
    cr = estimate_costs(al, geology=None, cfg=CostBands(), double_track=False)

    # Track cost always applies over the whole route.
    assert cr.subtotal_track > 0.0
    assert cr.total > 0.0
    # Contingency is applied on top of the base.
    assert np.isclose(cr.contingency_amount, cr.subtotal_base * cr.contingency_pct / 100.0)
    assert np.isclose(cr.total, cr.subtotal_base + cr.contingency_amount)


def test_double_track_costs_more(synthetic_profile):
    al = optimise(synthetic_profile, _params())
    single = estimate_costs(al, None, CostBands(), double_track=False)
    double = estimate_costs(al, None, CostBands(), double_track=True)
    assert double.subtotal_track > single.subtotal_track


def test_higher_contingency_raises_total(synthetic_profile):
    al = optimise(synthetic_profile, _params())
    low = estimate_costs(al, None, CostBands(contingency_pct=10.0))
    high = estimate_costs(al, None, CostBands(contingency_pct=30.0))
    assert high.total > low.total
    assert np.isclose(low.subtotal_base, high.subtotal_base)  # base unchanged by contingency
