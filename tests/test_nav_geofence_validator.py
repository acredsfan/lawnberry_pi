import pytest

pytest.importorskip("shapely")

from backend.src.nav.geofence_validator import build_shape, contains
from backend.src.models import Geofence, LatLng


def test_geofence_contains_and_buffer():
    # Square around origin ~10m radius
    square = [
        LatLng(latitude=0.0, longitude=0.0),
        LatLng(latitude=0.0, longitude=0.00009),
        LatLng(latitude=0.00009, longitude=0.00009),
        LatLng(latitude=0.00009, longitude=0.0),
    ]
    gf = Geofence(geofence_id="g1", boundary=square, buffer_distance_m=2.0)
    shape = build_shape(gf)

    inside = LatLng(latitude=0.000045, longitude=0.000045)
    outside = LatLng(latitude=0.0002, longitude=0.0002)

    assert contains(shape, inside, use_buffer=False)
    assert not contains(shape, outside, use_buffer=False)

    # With buffer, a point just outside original polygon should be contained
    slightly_outside = LatLng(latitude=0.00009 + 5.0 / 111000.0, longitude=0.0)
    assert contains(shape, slightly_outside, use_buffer=True)
