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


import json
from pathlib import Path

from backend.src.diagnostics.capture import TelemetryCapture


def test_telemetry_capture_writes_one_line_per_record(tmp_path: Path):
    capture = TelemetryCapture(tmp_path / "run.jsonl")
    record = CaptureRecord(
        capture_version=CAPTURE_SCHEMA_VERSION,
        record_type="nav_step",
        sensor_data=_sample_sensor_data(),
        navigation_state_after=_sample_snapshot(),
    )
    capture.record(record)
    capture.record(record)
    capture.close()

    lines = (tmp_path / "run.jsonl").read_text().splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["capture_version"] == CAPTURE_SCHEMA_VERSION
    assert parsed[0]["record_type"] == "nav_step"


def test_telemetry_capture_creates_parent_directory(tmp_path: Path):
    target = tmp_path / "nested" / "dir" / "run.jsonl"
    capture = TelemetryCapture(target)
    capture.record(
        CaptureRecord(
            capture_version=CAPTURE_SCHEMA_VERSION,
            record_type="nav_step",
            sensor_data=_sample_sensor_data(),
            navigation_state_after=_sample_snapshot(),
        )
    )
    capture.close()
    assert target.exists()
    assert target.parent.is_dir()


def test_telemetry_capture_flushes_each_record(tmp_path: Path):
    """A crash between records must leave a valid prefix on disk."""
    target = tmp_path / "run.jsonl"
    capture = TelemetryCapture(target)
    capture.record(
        CaptureRecord(
            capture_version=CAPTURE_SCHEMA_VERSION,
            record_type="nav_step",
            sensor_data=_sample_sensor_data(),
            navigation_state_after=_sample_snapshot(),
        )
    )
    # Without close(), the bytes should still be on disk because we flush per record.
    contents = target.read_text()
    assert contents.endswith("\n")
    json.loads(contents.strip())  # parses cleanly
    capture.close()


def test_telemetry_capture_close_is_idempotent(tmp_path: Path):
    capture = TelemetryCapture(tmp_path / "run.jsonl")
    capture.close()
    capture.close()  # must not raise
