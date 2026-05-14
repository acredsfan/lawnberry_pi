"""Tests for pure waypoint geometry helpers in backend.src.nav.waypoint_geometry."""

import pytest

from backend.src.nav.waypoint_geometry import (
    compute_blend_speeds,
    compute_tank_speeds,
    cross_track_error,
    heading_error,
    is_in_tank_mode,
    stanley_steer,
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
    """Baseline: stall_boost=0.0 with 90° turn denominator."""
    left, right = compute_blend_speeds(heading_err=-26.6, base_speed=0.5, stall_boost=0.0)
    # turn_effort = -26.6/90 = -0.296; forward ≈ 0.433 (0.5 * 0.867 taper)
    assert left == pytest.approx(0.305, abs=0.01)
    assert right == pytest.approx(0.561, abs=0.01)


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


# --- cross_track_error tests ---

def test_cross_track_zero_on_line():
    """A point on the line has zero cross-track error."""
    # Path going north; midpoint is on the line.
    a = (0.0, 0.0)
    b = (0.001, 0.0)   # ~111 m north
    mid = (0.0005, 0.0)
    assert cross_track_error(mid, a, b) == pytest.approx(0.0, abs=0.01)


def test_cross_track_signed_right_positive():
    """Point to the right of a northward path gives positive CTE."""
    a = (0.0, 0.0)
    b = (0.001, 0.0)
    p = (0.0005, 0.00001)  # slightly east = right of northward path
    assert cross_track_error(p, a, b) > 0.0


def test_cross_track_signed_left_negative():
    """Point to the left of a northward path gives negative CTE."""
    a = (0.0, 0.0)
    b = (0.001, 0.0)
    p = (0.0005, -0.00001)  # slightly west = left of northward path
    assert cross_track_error(p, a, b) < 0.0


def test_cross_track_one_meter_offset():
    """A 1 m lateral offset on a northward 100 m leg returns ~1.0 m CTE."""
    a = (0.0, 0.0)
    # ~100 m north
    b = (100.0 / 111_320.0, 0.0)
    # ~1 m east
    p = (50.0 / 111_320.0, 1.0 / 111_320.0)
    assert cross_track_error(p, a, b) == pytest.approx(1.0, abs=0.05)


def test_cross_track_degenerate_zero_length():
    """A→B of zero length returns 0 without errors."""
    a = (0.0, 0.0)
    assert cross_track_error((0.0, 0.0), a, a) == 0.0


def test_cross_track_eastward_path():
    """Right side of an eastward path is to the south (negative lat offset)."""
    a = (0.0, 0.0)
    b = (0.0, 0.001)   # eastward path
    # Point due south of midpoint (right of eastward path)
    p_south = (-0.00001, 0.0005)
    assert cross_track_error(p_south, a, b) > 0.0


# --- stanley_steer tests ---

def test_stanley_zero_cte_returns_heading_err():
    """With zero CTE, stanley_steer equals heading_err_deg (within dead-band)."""
    steer = stanley_steer(15.0, 0.0, 0.5)
    assert steer == pytest.approx(15.0, abs=0.01)


def test_stanley_dead_band_zeros_cte():
    """CTE within dead_band_m should produce same result as zero CTE."""
    steer_zero = stanley_steer(10.0, 0.0, 0.5, dead_band_m=0.1)
    steer_tiny = stanley_steer(10.0, 0.05, 0.5, dead_band_m=0.1)
    assert steer_zero == pytest.approx(steer_tiny, abs=0.01)


def test_stanley_right_of_path_gives_left_correction():
    """Positive CTE (right of path) should reduce / invert steer (left turn)."""
    steer_no_cte = stanley_steer(0.0, 0.0, 0.4)
    steer_right = stanley_steer(0.0, 1.0, 0.4)
    assert steer_right < steer_no_cte


def test_stanley_left_of_path_gives_right_correction():
    """Negative CTE (left of path) should increase steer (right turn)."""
    steer_no_cte = stanley_steer(0.0, 0.0, 0.4)
    steer_left = stanley_steer(0.0, -1.0, 0.4)
    assert steer_left > steer_no_cte


def test_stanley_low_speed_clamps_via_floor():
    """At standstill, v_floor prevents infinite steer from large CTE."""
    steer_slow = stanley_steer(0.0, 2.0, 0.0, v_floor=0.2)
    steer_floor = stanley_steer(0.0, 2.0, 0.2, v_floor=0.2)
    assert steer_slow == pytest.approx(steer_floor, abs=0.01)


def test_stanley_max_steer_clip():
    """Output is clipped to ±max_steer_deg."""
    # 80° heading err + large leftward CTE adding ~80° → raw steer ≈ 160° → clips to 60°
    steer = stanley_steer(80.0, -5.0, 0.5, max_steer_deg=60.0)
    assert steer == pytest.approx(60.0, abs=0.01)


# --- smooth_heading helper ---

def test_smooth_heading_clamps_large_jump():
    """A 30° raw jump with max_step_deg=8 should only advance by 8°."""
    from backend.src.nav.waypoint_geometry import smooth_heading
    result = smooth_heading(10.0, 40.0, alpha=0.12, max_step_deg=8.0)
    assert result == pytest.approx(18.0, abs=0.01)


def test_smooth_heading_wraps_across_zero():
    """359° → 5° should be treated as a +6° turn, not a -354° turn."""
    from backend.src.nav.waypoint_geometry import smooth_heading
    result = smooth_heading(359.0, 5.0, alpha=1.0, max_step_deg=90.0)
    # alpha=1.0 means fully adopt raw; shortest arc from 359→5 is +6°
    assert result == pytest.approx(5.0, abs=0.1)


def test_smooth_heading_wraps_across_360_backward():
    """5° → 359° should be treated as a -6° turn."""
    from backend.src.nav.waypoint_geometry import smooth_heading
    result = smooth_heading(5.0, 359.0, alpha=1.0, max_step_deg=90.0)
    assert result == pytest.approx(359.0, abs=0.1)


def test_smooth_heading_none_prev_returns_raw():
    """When prev is None, return raw unchanged."""
    from backend.src.nav.waypoint_geometry import smooth_heading
    result = smooth_heading(None, 135.0, alpha=0.3, max_step_deg=30.0)
    assert result == pytest.approx(135.0, abs=0.01)


# --- Stanley parameter validation (fail with current defaults) ---

def test_stanley_one_meter_cte_low_speed_stays_under_30deg():
    """With new defaults, 1m CTE at v=0.1 must produce ≤30° correction (not 71° as before)."""
    steer = stanley_steer(0.0, 1.0, 0.1)
    assert abs(steer) <= 30.0, f"steer={steer:.1f}° exceeds 30° limit"


def test_stanley_one_meter_cte_does_not_trigger_tank_mode():
    """1m CTE should never produce a steer large enough to enter tank mode (>60°)."""
    steer = stanley_steer(0.0, 1.0, 0.1)
    assert not is_in_tank_mode(abs(steer), currently_in_tank=False), \
        f"steer={steer:.1f}° would trigger tank mode"
