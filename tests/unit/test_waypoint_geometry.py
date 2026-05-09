"""Tests for pure waypoint geometry helpers in backend.src.nav.waypoint_geometry."""

import math
import pytest
from backend.src.nav.waypoint_geometry import (
    heading_error,
    compute_tank_speeds,
    compute_blend_speeds,
    is_in_tank_mode,
)


def test_heading_error_zero_when_aligned():
    assert heading_error(target=45.0, current=45.0) == pytest.approx(0.0)


def test_heading_error_positive_right_turn():
    err = heading_error(target=90.0, current=60.0)
    assert err == pytest.approx(30.0)


def test_heading_error_negative_left_turn():
    err = heading_error(target=30.0, current=60.0)
    assert err == pytest.approx(-30.0)


def test_heading_error_wraps_across_360():
    err = heading_error(target=10.0, current=350.0)
    assert err == pytest.approx(20.0, abs=0.01)


def test_heading_error_wraps_across_0():
    err = heading_error(target=350.0, current=10.0)
    assert err == pytest.approx(-20.0, abs=0.01)


def test_is_in_tank_mode_enters_above_60():
    assert is_in_tank_mode(abs_error=65.0, currently_in_tank=False) is True


def test_is_in_tank_mode_does_not_enter_below_60():
    assert is_in_tank_mode(abs_error=55.0, currently_in_tank=False) is False


def test_is_in_tank_mode_stays_in_until_below_50():
    assert is_in_tank_mode(abs_error=55.0, currently_in_tank=True) is True


def test_is_in_tank_mode_exits_below_50():
    assert is_in_tank_mode(abs_error=45.0, currently_in_tank=True) is False


def test_compute_tank_speeds_cw():
    left, right = compute_tank_speeds(heading_err=80.0, max_speed=0.8, stall_boost=0.0)
    assert left > 0
    assert right < 0


def test_compute_tank_speeds_ccw():
    left, right = compute_tank_speeds(heading_err=-80.0, max_speed=0.8, stall_boost=0.0)
    assert left < 0
    assert right > 0


def test_compute_tank_speeds_stall_boost_increases_magnitude():
    left_0, _ = compute_tank_speeds(heading_err=80.0, max_speed=0.8, stall_boost=0.0)
    left_b, _ = compute_tank_speeds(heading_err=80.0, max_speed=0.8, stall_boost=0.3)
    assert abs(left_b) > abs(left_0)


def test_compute_blend_speeds_straight_ahead():
    left, right = compute_blend_speeds(heading_err=0.0, base_speed=0.5, stall_boost=0.0)
    assert left == pytest.approx(right, abs=0.01)
    assert left > 0


def test_compute_blend_speeds_cw_turn_left_greater():
    left, right = compute_blend_speeds(heading_err=30.0, base_speed=0.5, stall_boost=0.0)
    assert left > right


def test_compute_blend_speeds_ccw_turn_right_greater():
    left, right = compute_blend_speeds(heading_err=-30.0, base_speed=0.5, stall_boost=0.0)
    assert right > left


def test_compute_blend_speeds_inner_wheel_floor():
    left, right = compute_blend_speeds(heading_err=60.0, base_speed=0.5, stall_boost=0.0)
    inner_min = 0.5 * 0.2
    assert right >= inner_min


def test_compute_blend_speeds_clamped_to_max_speed():
    left, right = compute_blend_speeds(
        heading_err=5.0, base_speed=0.8, stall_boost=0.0, max_speed=0.8
    )
    assert left <= 0.8
    assert right <= 0.8


def test_compute_tank_speeds_zero_error_returns_zero():
    left, right = compute_tank_speeds(heading_err=0.0, max_speed=0.8, stall_boost=0.0)
    assert left == 0.0
    assert right == 0.0


# --- stall_boost wired into blend (the actual root cause fix) ---

def test_compute_blend_speeds_stall_boost_zero_regression():
    """Baseline: stall_boost=0.0 produces the same result as before the fix."""
    left, right = compute_blend_speeds(heading_err=-26.6, base_speed=0.5, stall_boost=0.0)
    assert left == pytest.approx(0.177, abs=0.01)
    assert right == pytest.approx(0.691, abs=0.01)


def test_compute_blend_speeds_stall_boost_amplifies_both_wheels():
    """After 4 s of stall, both wheels must exceed stiction floor (0.5 × base_speed)."""
    left, right = compute_blend_speeds(heading_err=-26.6, base_speed=0.5, stall_boost=0.6)
    assert left >= 0.5 * 0.5, f"inner wheel too slow: left={left:.3f}"
    assert right >= 0.5 * 0.5, f"outer wheel too slow: right={right:.3f}"


def test_compute_blend_speeds_stall_boost_increases_output_over_no_boost():
    """Both wheel speeds must be strictly higher with boost than without."""
    left_0, right_0 = compute_blend_speeds(heading_err=-26.6, base_speed=0.5, stall_boost=0.0)
    left_b, right_b = compute_blend_speeds(heading_err=-26.6, base_speed=0.5, stall_boost=0.6)
    assert left_b > left_0
    assert right_b > right_0


def test_compute_blend_speeds_stall_boost_respects_max_speed():
    """Outer wheel must be capped at max_speed even with maximum boost."""
    _, right = compute_blend_speeds(
        heading_err=-26.6, base_speed=0.5, stall_boost=0.6, max_speed=0.8
    )
    assert right <= 0.8
