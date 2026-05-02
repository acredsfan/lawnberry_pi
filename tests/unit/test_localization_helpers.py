"""Tests for pure localization helper functions.

These tests have no async machinery, no fixtures, and no hardware. They
verify mathematical invariants only. Run with:
    SIM_MODE=1 uv run pytest tests/unit/test_localization_helpers.py -v
"""
import pytest


# --- heading_delta -----------------------------------------------------------

def test_heading_delta_zero_when_same():
    from backend.src.nav.localization_helpers import heading_delta
    assert heading_delta(90.0, 90.0) == pytest.approx(0.0)


def test_heading_delta_positive_for_clockwise_turn():
    from backend.src.nav.localization_helpers import heading_delta
    # Target is 30° clockwise from current
    assert heading_delta(60.0, 30.0) == pytest.approx(30.0)


def test_heading_delta_negative_for_counter_clockwise_turn():
    from backend.src.nav.localization_helpers import heading_delta
    assert heading_delta(30.0, 60.0) == pytest.approx(-30.0)


def test_heading_delta_wraps_across_zero():
    from backend.src.nav.localization_helpers import heading_delta
    # 350° target, 10° current → shortest path is -20° (CCW)
    assert heading_delta(350.0, 10.0) == pytest.approx(-20.0)


def test_heading_delta_180_is_max_magnitude():
    from backend.src.nav.localization_helpers import heading_delta
    result = heading_delta(180.0, 0.0)
    assert abs(result) == pytest.approx(180.0)


# --- wrap_heading ------------------------------------------------------------

def test_wrap_heading_no_op_within_range():
    from backend.src.nav.localization_helpers import wrap_heading
    assert wrap_heading(45.0) == pytest.approx(45.0)


def test_wrap_heading_360_becomes_0():
    from backend.src.nav.localization_helpers import wrap_heading
    assert wrap_heading(360.0) == pytest.approx(0.0)


def test_wrap_heading_negative_wraps_correctly():
    from backend.src.nav.localization_helpers import wrap_heading
    assert wrap_heading(-90.0) == pytest.approx(270.0)


def test_wrap_heading_large_positive():
    from backend.src.nav.localization_helpers import wrap_heading
    assert wrap_heading(720.0) == pytest.approx(0.0)


# --- apply_antenna_offset ----------------------------------------------------

def test_apply_antenna_offset_zero_offsets_returns_original():
    from backend.src.nav.localization_helpers import apply_antenna_offset
    lat, lon = apply_antenna_offset(
        gps_lat=40.0, gps_lon=-75.0,
        forward_m=0.0, right_m=0.0, heading_deg=0.0,
    )
    assert lat == pytest.approx(40.0)
    assert lon == pytest.approx(-75.0)


def test_apply_antenna_offset_forward_north_heading():
    """GPS antenna 0.5 m ahead of center, heading north → center is 0.5 m south of antenna."""
    from backend.src.nav.localization_helpers import apply_antenna_offset
    # forward_m = +0.5, heading = 0° (north).
    # Antenna is north of center, so center_lat = antenna_lat - 0.5/111320
    lat, lon = apply_antenna_offset(
        gps_lat=40.0, gps_lon=-75.0,
        forward_m=0.5, right_m=0.0, heading_deg=0.0,
    )
    # lat should be slightly less than 40.0
    expected_lat = 40.0 - 0.5 / 111_320.0
    assert lat == pytest.approx(expected_lat, rel=1e-6)
    assert lon == pytest.approx(-75.0, rel=1e-6)


def test_apply_antenna_offset_right_east_heading():
    """GPS antenna 0.3 m to the right, heading east → center is 0.3 m west of antenna."""
    from backend.src.nav.localization_helpers import apply_antenna_offset
    # right_m = +0.3, heading = 90° (east).
    # body right when heading east points south in world frame.
    # antenna_east_m = forward*sin(90) + right*cos(90) = 0 + 0.3*0 = 0.0
    # antenna_north_m = forward*cos(90) - right*sin(90) = 0 - 0.3 = -0.3
    # center = antenna - (antenna_north, antenna_east) → lat slightly more, lon same
    lat, lon = apply_antenna_offset(
        gps_lat=40.0, gps_lon=-75.0,
        forward_m=0.0, right_m=0.3, heading_deg=90.0,
    )
    # When heading east, right is south, so center is north of antenna
    # antenna_north = 0*cos(90) - 0.3*sin(90) = -0.3 → north offset applied negated → +0.3 north
    expected_lat = 40.0 + 0.3 / 111_320.0
    assert lat == pytest.approx(expected_lat, rel=1e-5)


def test_apply_antenna_offset_matches_navigation_service_logic():
    """Cross-check against the known test in test_navigation_service.py."""
    from backend.src.nav.localization_helpers import apply_antenna_offset
    # nav._gps_antenna_offset_forward_m = -0.46, heading = 0 (north)
    # Antenna is 0.46 m behind center → center is 0.46 m north of antenna
    lat, lon = apply_antenna_offset(
        gps_lat=40.0, gps_lon=-75.0,
        forward_m=-0.46, right_m=0.0, heading_deg=0.0,
    )
    expected_lat = 40.0 + 0.46 / 111_320.0
    assert lat == pytest.approx(expected_lat, rel=1e-6)
    assert lon == pytest.approx(-75.0, rel=1e-9)


# --- resolve_gps_cog_from_inputs --------------------------------------------

def test_resolve_gps_cog_uses_receiver_when_fast_enough():
    from backend.src.nav.localization_helpers import resolve_gps_cog_from_inputs
    cog, speed, source = resolve_gps_cog_from_inputs(
        receiver_heading=45.0,
        receiver_speed=0.5,
        derived_cog=None,
        derived_speed=None,
        speed_threshold=0.3,
    )
    assert cog == pytest.approx(45.0)
    assert source == "receiver"


def test_resolve_gps_cog_ignores_receiver_below_threshold():
    from backend.src.nav.localization_helpers import resolve_gps_cog_from_inputs
    cog, speed, source = resolve_gps_cog_from_inputs(
        receiver_heading=45.0,
        receiver_speed=0.1,      # below threshold
        derived_cog=90.0,
        derived_speed=0.4,
        speed_threshold=0.3,
    )
    assert cog == pytest.approx(90.0)
    assert source == "position_delta"


def test_resolve_gps_cog_returns_none_when_nothing_available():
    from backend.src.nav.localization_helpers import resolve_gps_cog_from_inputs
    cog, speed, source = resolve_gps_cog_from_inputs(
        receiver_heading=None,
        receiver_speed=None,
        derived_cog=None,
        derived_speed=None,
        speed_threshold=0.3,
    )
    assert cog is None
    assert source is None


def test_resolve_gps_cog_wraps_receiver_heading():
    from backend.src.nav.localization_helpers import resolve_gps_cog_from_inputs
    cog, _, _ = resolve_gps_cog_from_inputs(
        receiver_heading=400.0,  # should wrap to 40°
        receiver_speed=0.5,
        derived_cog=None,
        derived_speed=None,
        speed_threshold=0.3,
    )
    assert cog == pytest.approx(40.0)
