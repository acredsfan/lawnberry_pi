from backend.src.models.safety_limits import SafetyLimits
from backend.src.nav.obstacle_clearance import required_obstacle_clearance_m


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


def test_unknown_speed_uses_conservative_floor():
    limits = SafetyLimits(
        tof_obstacle_distance_meters=0.2,
        obstacle_min_clearance_m=0.55,
        obstacle_conservative_unknown_speed_mps=0.5,
    )

    assert required_obstacle_clearance_m(None, limits) >= 0.55


def test_threshold_only_limits_preserve_legacy_clearance():
    limits = type("Limits", (), {"tof_obstacle_distance_meters": 0.2})()

    assert required_obstacle_clearance_m(0.8, limits) == 0.2
