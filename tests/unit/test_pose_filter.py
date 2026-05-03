"""Unit tests for PoseFilter (real EKF replacing SimpleEKF placeholder)."""
from __future__ import annotations

import math
import time

import numpy as np
import pytest

from backend.src.fusion.ekf import PoseFilter
from backend.src.fusion.pose2d import PoseQuality


@pytest.fixture
def pf() -> PoseFilter:
    f = PoseFilter()
    f.reset(x_m=0.0, y_m=0.0, heading_deg=0.0)
    return f


# --- Predict ---

def test_predict_zero_dt_no_change(pf: PoseFilter):
    pf.predict(dt=0.0, distance_m=1.0)
    pose = pf.get_pose()
    assert pose.x_m == pytest.approx(0.0)
    assert pose.y_m == pytest.approx(0.0)


def test_predict_straight_north(pf: PoseFilter):
    """heading=0° → cos(0)=1 → x increases; heading 0° = east in ENU motion model."""
    pf.reset(x_m=0.0, y_m=0.0, heading_deg=0.0)
    pf.predict(dt=1.0, distance_m=1.0, delta_heading_deg=0.0)
    pose = pf.get_pose()
    assert pose.x_m == pytest.approx(1.0, abs=1e-6)
    assert pose.y_m == pytest.approx(0.0, abs=1e-6)


def test_predict_90deg_heading(pf: PoseFilter):
    """heading=90° → cos(90)=0, sin(90)=1 → y increases."""
    pf.reset(x_m=0.0, y_m=0.0, heading_deg=90.0)
    pf.predict(dt=1.0, distance_m=1.0, delta_heading_deg=0.0)
    pose = pf.get_pose()
    assert pose.x_m == pytest.approx(0.0, abs=1e-6)
    assert pose.y_m == pytest.approx(1.0, abs=1e-6)


def test_predict_velocity_derived_from_distance_and_dt(pf: PoseFilter):
    pf.predict(dt=2.0, distance_m=1.0)
    pose = pf.get_pose()
    assert pose.velocity_mps == pytest.approx(0.5, abs=1e-6)


def test_predict_heading_accumulates(pf: PoseFilter):
    pf.reset(heading_deg=0.0)
    pf.predict(dt=1.0, distance_m=0.0, delta_heading_deg=10.0)
    pf.predict(dt=1.0, distance_m=0.0, delta_heading_deg=10.0)
    pose = pf.get_pose()
    assert pose.heading_deg == pytest.approx(20.0, abs=1e-6)


def test_predict_heading_wraps_at_360(pf: PoseFilter):
    pf.reset(heading_deg=350.0)
    pf.predict(dt=1.0, distance_m=0.0, delta_heading_deg=20.0)
    pose = pf.get_pose()
    assert pose.heading_deg == pytest.approx(10.0, abs=1e-6)


# --- GPS update ---

def test_gps_update_accepted_near_estimate(pf: PoseFilter):
    pf.predict(dt=1.0, distance_m=0.0)
    accepted = pf.update_gps(x_m=0.01, y_m=0.0, accuracy_m=1.0)
    assert accepted is True
    pose = pf.get_pose()
    # x should move toward 0.01
    assert 0.0 < pose.x_m <= 0.01


def test_gps_update_rejected_large_jump(pf: PoseFilter):
    """A 100-m jump with tight accuracy should be rejected by the innovation gate.

    Tight accuracy (0.01m) → small R → small S → large Mahalanobis distance → rejection.
    """
    pf.predict(dt=1.0, distance_m=0.0)
    accepted = pf.update_gps(x_m=100.0, y_m=0.0, accuracy_m=0.01)
    assert accepted is False


def test_gps_update_sets_gps_timestamp(pf: PoseFilter):
    before = time.monotonic()
    pf.update_gps(x_m=0.0, y_m=0.0, accuracy_m=1.0)
    after = time.monotonic()
    pose = pf.get_pose()
    assert pose.gps_timestamp_s is not None
    assert before <= pose.gps_timestamp_s <= after


# --- IMU heading update ---

def test_imu_heading_accepted_near_estimate(pf: PoseFilter):
    pf.reset(heading_deg=10.0)
    accepted = pf.update_imu_heading(12.0, quality="calibrated")
    assert accepted is True
    pose = pf.get_pose()
    assert 10.0 < pose.heading_deg < 12.0


def test_imu_heading_rejected_when_fault(pf: PoseFilter):
    accepted = pf.update_imu_heading(90.0, quality="fault")
    assert accepted is False


def test_imu_heading_wrap_handled(pf: PoseFilter):
    """Wrap-safe innovation: 358° state + 5° measurement = +7° difference, not -353°.

    After reset, P[2,2]=10.0 and R_imu=5.0, so S=15.0.  A 7° innovation gives
    mahl2 = 49/15 ≈ 3.27 < 6.63 gate → accepted.  The state heading should
    advance slightly from 358° toward 5° (crossing 0).
    """
    pf.reset(heading_deg=358.0)
    accepted = pf.update_imu_heading(5.0, quality="calibrated")
    # Measurement is 7° CW from state; state should move toward 5° (crossing 0)
    assert accepted is True
    pose = pf.get_pose()
    # heading should be between 358 and 365 (≡ 5 deg)
    h = pose.heading_deg
    assert (h >= 358.0 and h <= 360.0) or (h >= 0.0 and h <= 5.0)


# --- Quality classification ---

def test_quality_stale_after_reset_no_updates(pf: PoseFilter):
    # After reset with no measurements, quality depends on predict timestamp
    # Predict sets filter_timestamp_s; no GPS → DEAD_RECKONING or STALE
    pf.predict(dt=0.1, distance_m=0.0)
    pose = pf.get_pose()
    # No GPS ever → DEAD_RECKONING or STALE
    assert pose.quality in (PoseQuality.DEAD_RECKONING, PoseQuality.STALE)


def test_quality_gps_degraded_after_gps_update(pf: PoseFilter):
    pf.predict(dt=0.1)
    pf.update_gps(0.0, 0.0, accuracy_m=3.0)
    pose = pf.get_pose()
    assert pose.quality == PoseQuality.GPS_DEGRADED


def test_quality_rtk_fixed(pf: PoseFilter):
    pf.predict(dt=0.1)
    pf.update_gps(0.0, 0.0, accuracy_m=0.02)
    pose = pf.get_pose()
    assert pose.quality == PoseQuality.RTK_FIXED


def test_quality_gps_float(pf: PoseFilter):
    pf.predict(dt=0.1)
    pf.update_gps(0.0, 0.0, accuracy_m=0.5)
    pose = pf.get_pose()
    assert pose.quality == PoseQuality.GPS_FLOAT


def test_quality_dead_reckoning_when_gps_stale(pf: PoseFilter, monkeypatch):
    """If last GPS was > STALE_THRESHOLD_S ago, quality = DEAD_RECKONING."""
    import backend.src.fusion.pose2d as p2d_mod
    pf.predict(dt=0.1)
    pf.update_gps(0.0, 0.0, accuracy_m=0.5)
    # Simulate time passing by back-dating the GPS timestamp
    old_ts = pf._last_gps_ts
    pf._last_gps_ts = old_ts - (p2d_mod.STALE_THRESHOLD_S + 1)
    pf._last_imu_ts = time.monotonic()  # IMU is still fresh
    pf._last_predict_ts = time.monotonic()
    pose = pf.get_pose()
    assert pose.quality == PoseQuality.DEAD_RECKONING
