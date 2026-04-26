"""Unit tests for diagnostics capture record models."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.src.models.diagnostics_capture import (
    CaptureRecord,
    NavigationStateSnapshot,
    CAPTURE_SCHEMA_VERSION,
)
from backend.src.models.navigation_state import NavigationMode, PathStatus, Position
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData


def _sample_sensor_data() -> SensorData:
    return SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0, accuracy=0.5, satellites=12),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )


def _sample_snapshot() -> NavigationStateSnapshot:
    return NavigationStateSnapshot(
        current_position=Position(latitude=42.0, longitude=-83.0),
        heading=90.0,
        gps_cog=92.0,
        velocity=0.4,
        target_velocity=0.5,
        current_waypoint_index=0,
        path_status=PathStatus.EXECUTING,
        navigation_mode=NavigationMode.AUTO,
        dead_reckoning_active=False,
        dead_reckoning_drift=None,
        last_gps_fix=datetime(2026, 4, 26, tzinfo=UTC),
    )


def test_capture_record_round_trip_via_json():
    record = CaptureRecord(
        capture_version=CAPTURE_SCHEMA_VERSION,
        record_type="nav_step",
        sensor_data=_sample_sensor_data(),
        navigation_state_after=_sample_snapshot(),
    )
    line = record.model_dump_json()
    restored = CaptureRecord.model_validate_json(line)
    assert restored.capture_version == CAPTURE_SCHEMA_VERSION
    assert restored.record_type == "nav_step"
    assert restored.sensor_data.gps is not None
    assert restored.sensor_data.gps.latitude == 42.0
    assert restored.navigation_state_after.heading == 90.0
    assert restored.navigation_state_after.path_status == "executing"


def test_capture_record_rejects_unknown_record_type():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CaptureRecord(
            capture_version=CAPTURE_SCHEMA_VERSION,
            record_type="not_a_real_type",
            sensor_data=_sample_sensor_data(),
            navigation_state_after=_sample_snapshot(),
        )


def test_navigation_state_snapshot_excludes_path_lists():
    snap = _sample_snapshot()
    dumped = snap.model_dump()
    assert "planned_path" not in dumped
    assert "obstacle_map" not in dumped
    assert "coverage_grid" not in dumped
    assert "safety_boundaries" not in dumped
