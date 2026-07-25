"""Input-limit validation (pure, no network)."""
import pytest
from fastapi import HTTPException

from validation import route_length_km, validate_waypoints, MAX_WAYPOINTS


def test_route_length_km_equator():
    # 1° of longitude at the equator ≈ 111.32 km
    assert abs(route_length_km([[0.0, 0.0], [0.0, 1.0]]) - 111.32) < 1.0


def test_validate_ok_returns_length():
    length = validate_waypoints([[-33.87, 151.21], [-33.80, 151.28]])
    assert 0 < length < 20


def test_rejects_too_few():
    with pytest.raises(HTTPException) as e:
        validate_waypoints([[0.0, 0.0]])
    assert e.value.status_code == 422


def test_rejects_too_many():
    wps = [[-33.0 + i * 0.0001, 151.0] for i in range(MAX_WAYPOINTS + 1)]
    with pytest.raises(HTTPException) as e:
        validate_waypoints(wps)
    assert e.value.status_code == 422


def test_rejects_out_of_range_coord():
    with pytest.raises(HTTPException) as e:
        validate_waypoints([[91.0, 0.0], [0.0, 0.0]])
    assert e.value.status_code == 422


def test_rejects_too_long_route():
    # Opposite ends of the planet — far exceeds MAX_ROUTE_KM
    with pytest.raises(HTTPException) as e:
        validate_waypoints([[-33.0, 151.0], [33.0, 10.0]])
    assert e.value.status_code == 422
