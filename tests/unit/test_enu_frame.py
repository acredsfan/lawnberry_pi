"""Unit tests for ENUFrame WGS84 ↔ ENU converter."""
from __future__ import annotations

import math
import pytest
from backend.src.fusion.enu_frame import ENUFrame


@pytest.fixture
def frame_michigan() -> ENUFrame:
    """Frame anchored at 42.0°N, -83.0°E (Detroit area, same as fixture)."""
    f = ENUFrame()
    f.set_origin(42.0, -83.0)
    return f


def test_origin_maps_to_zero(frame_michigan: ENUFrame):
    x, y = frame_michigan.to_local(42.0, -83.0)
    assert abs(x) < 1e-9
    assert abs(y) < 1e-9


def test_north_movement_positive_y(frame_michigan: ENUFrame):
    """Moving north (lat+) should increase y_m."""
    x, y = frame_michigan.to_local(42.001, -83.0)
    assert y > 0
    assert abs(x) < 0.01  # essentially zero east displacement


def test_east_movement_positive_x(frame_michigan: ENUFrame):
    """Moving east (lon+) should increase x_m."""
    x, y = frame_michigan.to_local(42.0, -82.999)
    assert x > 0
    assert abs(y) < 0.01


def test_100m_north_accuracy(frame_michigan: ENUFrame):
    """100 m north movement: LAT_STEP = 100/111320 degrees."""
    lat_step = 100.0 / 111_320.0
    x, y = frame_michigan.to_local(42.0 + lat_step, -83.0)
    assert abs(y - 100.0) < 0.01  # flat-earth accurate to cm at 100 m


def test_round_trip_wgs84(frame_michigan: ENUFrame):
    lat_in, lon_in = 42.001, -82.998
    x, y = frame_michigan.to_local(lat_in, lon_in)
    lat_out, lon_out = frame_michigan.to_wgs84(x, y)
    assert abs(lat_out - lat_in) < 1e-9
    assert abs(lon_out - lon_in) < 1e-9


def test_unanchored_raises():
    f = ENUFrame()
    with pytest.raises(RuntimeError, match="no origin"):
        f.to_local(42.0, -83.0)


def test_is_anchored_false_before_set():
    assert not ENUFrame().is_anchored


def test_is_anchored_true_after_set(frame_michigan: ENUFrame):
    assert frame_michigan.is_anchored
