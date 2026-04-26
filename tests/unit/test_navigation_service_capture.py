"""Tests for the optional capture hook on NavigationService."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.diagnostics.replay import ReplayLoader
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData
from backend.src.services.navigation_service import NavigationService


@pytest.mark.asyncio
async def test_navigation_service_records_step_when_capture_attached(tmp_path: Path):
    capture_path = tmp_path / "nav.jsonl"
    capture = TelemetryCapture(capture_path)

    # Construct a fresh NavigationService (do not use the singleton; tests must
    # not pollute global state).
    nav = NavigationService()
    nav.attach_capture(capture)

    sensor_data = SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0, accuracy=0.5, satellites=12),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )
    await nav.update_navigation_state(sensor_data)
    capture.close()

    records = list(ReplayLoader(capture_path))
    assert len(records) == 1
    assert records[0].record_type == "nav_step"
    assert records[0].sensor_data.gps is not None
    assert records[0].sensor_data.gps.latitude == 42.0


@pytest.mark.asyncio
async def test_navigation_service_records_nothing_without_capture(tmp_path: Path):
    """Behavior must be unchanged when no capture is attached."""
    nav = NavigationService()
    sensor_data = SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )
    # Should not raise, should not write anything.
    result = await nav.update_navigation_state(sensor_data)
    assert result is not None  # returns NavigationState as before


@pytest.mark.asyncio
async def test_navigation_service_capture_failure_does_not_break_navigation(
    tmp_path: Path, monkeypatch
):
    """If capture.record raises, navigation must still return a state."""
    nav = NavigationService()

    class BrokenCapture:
        def record(self, _record):
            raise OSError("simulated disk full")

        def close(self):
            pass

    nav.attach_capture(BrokenCapture())  # type: ignore[arg-type]
    sensor_data = SensorData(
        gps=GpsReading(latitude=42.0, longitude=-83.0),
        imu=ImuReading(yaw=90.0, calibration_status="calibrated"),
    )
    result = await nav.update_navigation_state(sensor_data)
    assert result is not None
