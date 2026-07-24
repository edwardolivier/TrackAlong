"""Geology engineering classification (no network — pure keyword logic)."""
import pytest

from core.geology import classify


@pytest.mark.parametrize(
    "unit, lith, age, expected",
    [
        ("Sydney Granite", "granite", "Triassic", "A"),        # hard rock
        ("Hawkesbury", "sandstone", "Triassic", "B"),          # medium rock
        ("Wianamatta", "shale", "Triassic", "C"),              # weak rock
        ("Floodplain", "alluvium", "Quaternary", "D"),         # soft ground
        ("Recent deposits", "", "Holocene", "D"),              # soft by age
        ("Basalt flow", "basalt", "Holocene", "A"),            # rock keyword beats young age
        ("Mystery", "unobtainium", "", "?"),                   # unknown
        ("Unit", "feldspathic sandstone", "", "B"),            # partial/compound match
    ],
)
def test_classify(unit, lith, age, expected):
    assert classify(unit, lith, age) == expected
