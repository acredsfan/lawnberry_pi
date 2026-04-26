"""Unit tests for diagnostics replay loader."""
from __future__ import annotations

import pytest
from pathlib import Path

from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.diagnostics.replay import ReplayLoader, ReplayLoadError
from backend.src.models.diagnostics_capture import (
    CAPTURE_SCHEMA_VERSION,
    CaptureRecord,
    NavigationStateSnapshot,
)
from backend.src.models.navigation_state import NavigationMode, PathStatus, Position
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData


def _record(seq: int = 0) -> CaptureRecord:
    return CaptureRecord(
        capture_version=CAPTURE_SCHEMA_VERSION,
        record_type="nav_step",
        sensor_data=SensorData(
            gps=GpsReading(latitude=42.0 + seq * 0.0001, longitude=-83.0),
            imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
        ),
        navigation_state_after=NavigationStateSnapshot(
            current_position=Position(latitude=42.0 + seq * 0.0001, longitude=-83.0),
            heading=90.0,
            current_waypoint_index=0,
            path_status=PathStatus.EXECUTING,
            navigation_mode=NavigationMode.AUTO,
        ),
    )


def test_replay_loader_round_trips_through_capture(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    capture = TelemetryCapture(target)
    for i in range(3):
        capture.record(_record(i))
    capture.close()

    records = list(ReplayLoader(target))
    assert len(records) == 3
    for i, rec in enumerate(records):
        assert rec.sensor_data.gps is not None
        assert rec.sensor_data.gps.latitude == pytest.approx(42.0 + i * 0.0001)


def test_replay_loader_skips_blank_lines(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    capture = TelemetryCapture(target)
    capture.record(_record(0))
    capture.close()
    # Inject blank lines.
    with target.open("a", encoding="utf-8") as fp:
        fp.write("\n   \n")
    records = list(ReplayLoader(target))
    assert len(records) == 1


def test_replay_loader_surfaces_line_number_on_corrupt_record(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    target.write_text(
        '{"capture_version":1,"record_type":"nav_step","sensor_data":{},'
        '"navigation_state_after":{}}\n'
        "this is not json\n",
        encoding="utf-8",
    )
    with pytest.raises(ReplayLoadError) as excinfo:
        list(ReplayLoader(target))
    assert "line 2" in str(excinfo.value)


def test_replay_loader_rejects_mismatched_schema_version(tmp_path: Path):
    target = tmp_path / "run.jsonl"
    target.write_text(
        '{"capture_version":999,"record_type":"nav_step",'
        '"sensor_data":{},"navigation_state_after":{}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ReplayLoadError) as excinfo:
        list(ReplayLoader(target))
    assert "schema" in str(excinfo.value).lower()


def test_replay_loader_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        list(ReplayLoader(tmp_path / "does-not-exist.jsonl"))
