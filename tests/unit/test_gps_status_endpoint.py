from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.src.api.routers import sensors as sensors_router
from backend.src.models.sensor_data import GpsMode, GpsReading


@pytest.mark.asyncio
async def test_gps_status_is_read_only_and_reports_real_sample_age(monkeypatch):
    class FakeDriver:
        async def health_check(self):
            return {
                "initialized": True,
                "running": True,
                "last_read_age_s": 42.0,
                "live": False,
                "stale": True,
                "serial_reopen_count": 3,
            }

    class FakeGps:
        gps_mode = GpsMode.F9P_USB
        status = "online"
        _driver = FakeDriver()
        last_reading = GpsReading(
            latitude=42.0,
            longitude=-83.0,
            accuracy=0.03,
            rtk_status="RTK_FIXED",
            timestamp=datetime.now(UTC) - timedelta(seconds=42),
            sample_id=91,
            cached=True,
        )

        async def read_gps(self):
            raise AssertionError("status endpoint must not compete with the GPS owner")

    async def fake_sensor_manager():
        return SimpleNamespace(gps=FakeGps())

    monkeypatch.setattr(
        sensors_router.websocket_hub,
        "_ensure_sensor_manager",
        fake_sensor_manager,
    )

    status = await sensors_router.get_gps_status()

    assert status.mode == GpsMode.F9P_USB.value
    assert status.last_read_age_s == pytest.approx(42.0)
    assert status.cached is True
    assert status.live is False
    assert status.sample_id == 91
    assert status.stale_reason == "cached_sample"
    assert status.serial_reopen_count == 3
