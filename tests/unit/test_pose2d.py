"""Unit tests for Pose2D and PoseQuality."""
from __future__ import annotations

from backend.src.fusion.pose2d import STALE_THRESHOLD_S, Pose2D, PoseQuality


def test_default_quality_is_stale():
    p = Pose2D()
    assert p.quality == PoseQuality.STALE


def test_distance_to_zero_origin():
    p = Pose2D(x_m=3.0, y_m=4.0)
    assert abs(p.distance_to(Pose2D()) - 5.0) < 1e-9


def test_heading_error_wraps():
    p = Pose2D(heading_deg=350.0)
    # 10° CCW from 350° is 0° → error should be +10
    assert abs(p.heading_error_deg(0.0) - 10.0) < 1e-9
    # 340° CW → error should be -10
    assert abs(p.heading_error_deg(340.0) + 10.0) < 1e-9


def test_pose_quality_enum_values():
    assert PoseQuality.RTK_FIXED == "rtk_fixed"
    assert PoseQuality.GPS_FLOAT == "gps_float"
    assert PoseQuality.GPS_DEGRADED == "gps_degraded"
    assert PoseQuality.DEAD_RECKONING == "dead_reckoning"
    assert PoseQuality.STALE == "stale"


def test_stale_threshold_positive():
    assert STALE_THRESHOLD_S > 0
