"""Generate the synthetic_straight_drive.jsonl golden fixture.

Run with:

    SIM_MODE=1 python -m tests.fixtures.navigation.build_synthetic_fixture

This script constructs a fresh NavigationService in SIM_MODE, feeds it a
deterministic sequence of SensorData snapshots, and writes the resulting
CaptureRecord stream to synthetic_straight_drive.jsonl in this directory.

The fixture is committed to the repository. Tests load it via ReplayLoader and
replay through the current code path to verify parity. If a navigation change
intentionally alters the output for this scenario, regenerate the fixture and
review the diff carefully — every committed fixture change is a behavior change.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.src.diagnostics.capture import TelemetryCapture
from backend.src.models.sensor_data import GpsReading, ImuReading, SensorData
from backend.src.services.navigation_service import NavigationService


FIXTURE_PATH = Path(__file__).parent / "synthetic_straight_drive.jsonl"
NUM_STEPS = 5
LAT_START = 42.0
LON_START = -83.0
LAT_STEP = 0.0001  # ~11 m at 42°N
YAW_DEG = 90.0


async def _build() -> None:
    # Force SIM mode so navigation does not attempt hardware access.
    os.environ.setdefault("SIM_MODE", "1")

    # Fresh service — do not pollute the singleton.
    nav = NavigationService()
    capture = TelemetryCapture(FIXTURE_PATH)
    nav.attach_capture(capture)

    base_time = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
    for i in range(NUM_STEPS):
        ts = base_time + timedelta(seconds=i)
        sensor_data = SensorData(
            gps=GpsReading(
                latitude=LAT_START + i * LAT_STEP,
                longitude=LON_START,
                altitude=200.0,
                accuracy=0.5,
                heading=YAW_DEG,
                speed=0.5,
                satellites=12,
                hdop=0.8,
                timestamp=ts,
            ),
            imu=ImuReading(
                yaw=YAW_DEG,
                roll=0.0,
                pitch=0.0,
                calibration_status="calibrated",
                timestamp=ts,
            ),
            timestamp=ts,
        )
        await nav.update_navigation_state(sensor_data)
    capture.close()
    print(f"Wrote {NUM_STEPS} records to {FIXTURE_PATH}")


if __name__ == "__main__":
    asyncio.run(_build())
