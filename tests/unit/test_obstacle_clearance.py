import pytest

from backend.src.models.safety_limits import SafetyLimits
from backend.src.nav.obstacle_clearance import (
    configured_tof_obstacle_threshold_m,
    required_obstacle_clearance_m,
)


def test_required_clearance_increases_with_speed():
    limits = SafetyLimits(
        tof_obstacle_distance_meters=0.2,
        obstacle_min_clearance_m=0.3,
        obstacle_detection_latency_s=0.2,
        obstacle_conservative_deceleration_mps2=0.5,
        obstacle_front_offset_m=0.1,
        obstacle_fixed_margin_m=0.1,
    )

    low = required_obstacle_clearance_m(0.2, limits)
    high = required_obstacle_clearance_m(0.8, limits)

    assert high > low


def test_unknown_speed_uses_conservative_stopping_model():
    limits = SafetyLimits(
        tof_obstacle_distance_meters=0.0254,
        obstacle_min_clearance_m=0.15,
        obstacle_detection_latency_s=0.35,
        obstacle_conservative_deceleration_mps2=0.45,
        obstacle_fixed_margin_m=0.10,
        obstacle_conservative_unknown_speed_mps=0.4,
    )

    assert required_obstacle_clearance_m(None, limits) == pytest.approx(0.417777, abs=1e-5)


def test_threshold_only_limits_preserve_legacy_clearance():
    limits = type("Limits", (), {"tof_obstacle_distance_meters": 0.2})()

    assert required_obstacle_clearance_m(0.8, limits) == 0.2


def test_configured_tof_threshold_matches_operator_setting_without_dynamic_floor():
    limits = SafetyLimits(
        tof_obstacle_distance_meters=0.0254,
        obstacle_min_clearance_m=0.15,
        obstacle_front_offset_m=0.25,
        obstacle_fixed_margin_m=0.10,
    )

    assert configured_tof_obstacle_threshold_m(limits) == 0.0254
    assert required_obstacle_clearance_m(0.0, limits) == 0.15


def test_front_sensor_offset_is_not_double_counted_in_measured_clearance():
    common = {
        "tof_obstacle_distance_meters": 0.0254,
        "obstacle_min_clearance_m": 0.15,
        "obstacle_detection_latency_s": 0.35,
        "obstacle_conservative_deceleration_mps2": 0.45,
        "obstacle_fixed_margin_m": 0.10,
    }
    short_offset = SafetyLimits(**common, obstacle_front_offset_m=0.10)
    long_offset = SafetyLimits(**common, obstacle_front_offset_m=0.50)

    expected = 0.12 * 0.35 + (0.12**2) / (2.0 * 0.45) + 0.10

    assert required_obstacle_clearance_m(0.12, short_offset) == pytest.approx(expected)
    assert required_obstacle_clearance_m(0.12, long_offset) == pytest.approx(expected)


def test_manual_cutoff_does_not_raise_full_autonomous_model_floor():
    limits = SafetyLimits(
        tof_obstacle_distance_meters=0.55,
        obstacle_min_clearance_m=0.15,
        obstacle_fixed_margin_m=0.10,
    )

    assert required_obstacle_clearance_m(0.0, limits) == 0.15
