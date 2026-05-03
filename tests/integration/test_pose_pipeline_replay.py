"""Straight-line replay test for PoseFilter (§3 acceptance criterion).

Feeds the committed synthetic straight-drive fixture through ENUFrame +
PoseFilter and asserts that the estimated ENU displacement matches the
known GPS-derived ground truth within tolerances:
  - distance: within 5% of true value (~44.5m north)
  - quality: GPS-based (not stale, not dead reckoning)

EKF heading convention note: PoseFilter.predict() uses math convention,
not compass convention. heading_deg=90 moves in the +y (north) direction in
the ENU frame. The fixture IMU yaw is 90°, which in the EKF's math convention
corresponds to northward motion, matching the GPS trajectory.
"""
from __future__ import annotations

import math
from pathlib import Path

from backend.src.diagnostics.replay import ReplayLoader
from backend.src.fusion.ekf import PoseFilter
from backend.src.fusion.enu_frame import ENUFrame
from backend.src.fusion.pose2d import Pose2D, PoseQuality

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "navigation"
    / "synthetic_straight_drive.jsonl"
)

DISTANCE_TOLERANCE_PCT = 5.0

# Ground truth: 4 movements × LAT_STEP × metres-per-degree
# Fixture: latitude increments 0.0001° per step, longitude stays fixed → pure north
_LAT_STEP = 0.0001
_STEPS_MOVED = 4
_METERS_PER_DEG_LAT = 111_320.0
TRUE_NORTH_M = _STEPS_MOVED * _LAT_STEP * _METERS_PER_DEG_LAT  # ≈ 44.528 m


def test_straight_line_replay_pose_within_tolerance():
    """Feed the synthetic fixture through ENUFrame + PoseFilter and verify ENU output."""
    assert FIXTURE.exists(), f"Missing fixture: {FIXTURE}"

    records = list(ReplayLoader(FIXTURE))
    assert len(records) == 5, f"Expected 5 fixture records, got {len(records)}"

    # --- Setup ENU frame anchored at the first GPS fix ---
    first_gps = records[0].sensor_data.gps
    assert first_gps is not None, "First record has no GPS data"

    frame = ENUFrame()
    frame.set_origin(first_gps.latitude, first_gps.longitude)

    # --- Setup PoseFilter ---
    pf = PoseFilter()
    # Reset at origin with heading=90.  In the EKF's math-convention predict step,
    # heading=90° maps to cos(90°)=0 east, sin(90°)=1 north, so the filter expects
    # northward motion — matching the fixture's GPS trajectory.
    first_imu = records[0].sensor_data.imu
    initial_heading = first_imu.yaw if first_imu is not None else 90.0
    pf.reset(x_m=0.0, y_m=0.0, heading_deg=initial_heading)

    final_pose: Pose2D | None = None
    prev_x_m: float = 0.0
    prev_y_m: float = 0.0

    for i, record in enumerate(records):
        sd = record.sensor_data
        gps = sd.gps
        imu = sd.imu

        # Convert GPS to ENU
        if gps is not None:
            x_m, y_m = frame.to_local(gps.latitude, gps.longitude)
        else:
            x_m, y_m = prev_x_m, prev_y_m

        # Predict step: propagate state forward using the GPS-derived step distance.
        # Between records the mower moved from prev_pos to current GPS pos.
        # Using dt=1.0 s (fixture has 1-second intervals).
        if i > 0:
            step_dist = math.sqrt((x_m - prev_x_m) ** 2 + (y_m - prev_y_m) ** 2)
            pf.predict(dt=1.0, distance_m=step_dist, delta_heading_deg=0.0)

        # Apply GPS measurement
        if gps is not None:
            accuracy = gps.accuracy if gps.accuracy is not None else 5.0
            pf.update_gps(x_m=x_m, y_m=y_m, accuracy_m=accuracy)

        # Apply IMU heading measurement
        if imu is not None:
            quality_str = imu.calibration_status or "calibrated"
            pf.update_imu_heading(heading_deg=imu.yaw, quality=quality_str)

        prev_x_m, prev_y_m = x_m, y_m
        final_pose = pf.get_pose()

    assert final_pose is not None, "No pose produced from fixture replay"

    # --- Distance assertion ---
    # The fixture moves north only (longitude fixed), so x_m ≈ 0, y_m ≈ TRUE_NORTH_M.
    estimated_distance_m = math.sqrt(final_pose.x_m ** 2 + final_pose.y_m ** 2)

    pct_error = abs(estimated_distance_m - TRUE_NORTH_M) / TRUE_NORTH_M * 100.0
    assert pct_error <= DISTANCE_TOLERANCE_PCT, (
        f"Distance error {pct_error:.1f}% exceeds {DISTANCE_TOLERANCE_PCT}% tolerance. "
        f"Estimated: {estimated_distance_m:.3f} m, True: {TRUE_NORTH_M:.3f} m, "
        f"pose=(x={final_pose.x_m:.3f}, y={final_pose.y_m:.3f})"
    )

    # --- Quality assertion ---
    # Fixture GPS accuracy is 0.5 m (<= 1.0 m threshold) → GPS_FLOAT or better
    gps_qualities = (
        PoseQuality.GPS_DEGRADED,
        PoseQuality.GPS_FLOAT,
        PoseQuality.RTK_FIXED,
    )
    assert final_pose.quality in gps_qualities, (
        f"Expected GPS-based quality (one of {[q.value for q in gps_qualities]}), "
        f"got {final_pose.quality!r}"
    )
