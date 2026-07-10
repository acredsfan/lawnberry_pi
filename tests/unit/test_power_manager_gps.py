from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.src.models.sensor_data import GpsReading
from backend.src.services import power_manager as power_manager_module
from backend.src.services.power_manager import PowerManager


class FakeGpsDriver:
    def __init__(self, *, suspended: bool = False):
        self.is_suspended = suspended
        self.resume_calls = 0

    def resume(self):
        self.is_suspended = False
        self.resume_calls += 1


def _manager(driver: FakeGpsDriver, *, speed: float = 0.0):
    return SimpleNamespace(
        gps=SimpleNamespace(
            _driver=driver,
            last_reading=GpsReading(
                latitude=40.0,
                longitude=-75.0,
                speed=speed,
            ),
        ),
        imu=SimpleNamespace(last_reading=None),
    )


@pytest.mark.asyncio
async def test_dark_idle_tick_never_suspends_safety_critical_gps(monkeypatch):
    driver = FakeGpsDriver()
    manager = PowerManager()
    manager._sensor_manager = _manager(driver)
    manager._suspend_gps = AsyncMock(side_effect=AssertionError("GPS must remain live"))
    manager._set_victron_rate = AsyncMock()
    manager._pause_camera = AsyncMock()
    manager._soft_disable_ai = AsyncMock()
    manager._camera_idle_since = time.monotonic()
    monkeypatch.setattr(power_manager_module, "_is_dark", lambda _lat, _lon: True)
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    manager._suspend_gps.assert_not_awaited()
    assert driver.is_suspended is False


@pytest.mark.asyncio
async def test_resume_detects_driver_suspension_even_if_manager_flag_was_reset():
    driver = FakeGpsDriver(suspended=True)
    manager = PowerManager()
    manager._sensor_manager = _manager(driver)
    manager._gps_suspended = False

    await manager._resume_gps_if_suspended()

    assert driver.resume_calls == 1
    assert manager._gps_suspended is False


def test_motion_detection_uses_current_gps_speed_field():
    driver = FakeGpsDriver()
    manager = PowerManager()
    manager._sensor_manager = _manager(driver, speed=0.2)

    assert manager._is_moving() is True
