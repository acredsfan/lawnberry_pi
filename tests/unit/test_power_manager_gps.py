from __future__ import annotations

import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.src.models.sensor_data import GpsReading
from backend.src.services import ai_service as ai_service_module
from backend.src.services import camera_runtime as camera_runtime_module
from backend.src.services import power_manager as power_manager_module
from backend.src.services.power_manager import (
    PowerManager,
    _equation_of_time_minutes,
    _solar_elevation,
)


def test_v77_summer_afternoon_and_night_solar_elevation_are_classified_correctly():
    latitude = 39.1031
    longitude = -84.5120

    summer_afternoon_utc = datetime(2026, 7, 15, 20, 30, tzinfo=UTC)
    summer_night_utc = datetime(2026, 7, 15, 4, 30, tzinfo=UTC)

    assert _solar_elevation(latitude, longitude, summer_afternoon_utc) > 40.0
    assert _solar_elevation(latitude, longitude, summer_night_utc) < -6.0


@pytest.mark.parametrize("month", range(1, 13))
def test_v77_equation_of_time_stays_within_physical_bounds(month):
    sample = datetime(2026, month, 15, 12, 0, tzinfo=UTC)

    assert abs(_equation_of_time_minutes(sample)) < 20.0


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


@pytest.mark.asyncio
async def test_camera_power_cycle_uses_runtime_owner(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=True),
        start_streaming=AsyncMock(return_value=True),
    )

    async def stop_streaming():
        camera.stream.is_active = False

    camera.stop_streaming = AsyncMock(side_effect=stop_streaming)
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()

    await manager._pause_camera()

    camera.stop_streaming.assert_awaited_once_with()
    assert manager._camera_paused_by_pm is True

    camera.stream.is_active = False
    await manager._resume_camera_if_paused()

    camera.start_streaming.assert_awaited_once_with()
    assert manager._camera_paused_by_pm is False
    assert manager._camera_idle_since is None


@pytest.mark.asyncio
async def test_recent_operator_camera_demand_prevents_idle_pause(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=True),
        has_recent_activity=lambda _timeout: True,
        stop_streaming=AsyncMock(),
        start_streaming=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._camera_idle_since = time.monotonic() - 120.0
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    camera.stop_streaming.assert_not_awaited()
    assert manager._camera_idle_since is None


@pytest.mark.asyncio
async def test_recent_operator_camera_demand_resumes_power_paused_capture(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=False),
        has_recent_activity=lambda _timeout: True,
        stop_streaming=AsyncMock(),
        start_streaming=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._camera_paused_by_pm = True
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    camera.start_streaming.assert_awaited_once_with()
    assert manager._camera_paused_by_pm is False
    assert manager._camera_idle_since is None


@pytest.mark.asyncio
async def test_true_camera_idle_still_pauses_after_timeout(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=True),
        has_recent_activity=lambda _timeout: False,
        stop_streaming=AsyncMock(),
        start_streaming=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._camera_idle_since = time.monotonic() - 120.0
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    camera.stop_streaming.assert_awaited_once_with()
    assert manager._camera_paused_by_pm is True


@pytest.mark.asyncio
async def test_expired_viewer_lease_uses_one_total_idle_deadline(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=True),
        activity_age_seconds=lambda: power_manager_module.CAMERA_IDLE_TIMEOUT_S + 1.0,
        has_recent_activity=lambda _timeout: False,
        stop_streaming=AsyncMock(),
        start_streaming=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    manager._soft_disable_ai = AsyncMock()
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    camera.stop_streaming.assert_awaited_once_with()
    assert manager._camera_paused_by_pm is True


@pytest.mark.asyncio
async def test_active_mission_restarts_camera_not_paused_by_power_manager(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=False),
        activity_age_seconds=lambda: None,
        has_recent_activity=lambda _timeout: False,
        get_camera_status=AsyncMock(return_value={"is_active": False}),
        stop_streaming=AsyncMock(),
        start_streaming=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    manager._reenable_ai_if_disabled = AsyncMock()
    monkeypatch.setattr(manager, "_is_mission_active", lambda: True)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    camera.get_camera_status.assert_awaited_once_with()
    camera.start_streaming.assert_awaited_once_with()
    assert manager._camera_idle_since is None


@pytest.mark.asyncio
async def test_ai_power_gate_reaches_local_state_and_camera_owner(monkeypatch):
    local_calls: list[bool] = []
    local_ai = SimpleNamespace(set_enabled=lambda enabled: local_calls.append(enabled))
    camera = SimpleNamespace(set_ai_enabled=AsyncMock())
    monkeypatch.setattr(ai_service_module, "get_ai_service", lambda: local_ai)
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()

    await manager._soft_disable_ai()
    await manager._reenable_ai_if_disabled()

    assert local_calls == [False, True]
    assert camera.set_ai_enabled.await_args_list[0].args == (False,)
    assert camera.set_ai_enabled.await_args_list[1].args == (True,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dark,moving,viewer_active",
    [
        (True, False, True),
        (False, False, False),
        (True, True, False),
    ],
    ids=["viewer", "daylight", "manual-motion"],
)
async def test_dark_idle_ai_gate_reenables_for_every_active_transition(
    monkeypatch,
    dark,
    moving,
    viewer_active,
):
    manager = PowerManager()
    manager._ai_soft_disabled = True
    manager._set_ai_enabled = AsyncMock(return_value=True)
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    manager._ensure_camera_running = AsyncMock(return_value=True)
    manager._pause_camera = AsyncMock(return_value=True)
    monkeypatch.setattr(power_manager_module, "_is_dark", lambda _lat, _lon: dark)
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: moving)
    monkeypatch.setattr(
        manager,
        "_camera_activity_age_seconds",
        lambda: 0.0 if viewer_active else None,
    )
    monkeypatch.setattr(manager, "_camera_has_recent_demand", lambda: viewer_active)

    await manager._tick()

    manager._set_ai_enabled.assert_awaited_once_with(True)
    assert manager._ai_soft_disabled is False


@pytest.mark.asyncio
async def test_owner_ai_reenable_failure_stays_pending_and_retries(monkeypatch):
    local_calls: list[bool] = []
    local_ai = SimpleNamespace(set_enabled=lambda enabled: local_calls.append(enabled))
    camera = SimpleNamespace(
        set_ai_enabled=AsyncMock(side_effect=[RuntimeError("IPC unavailable"), None])
    )
    monkeypatch.setattr(ai_service_module, "get_ai_service", lambda: local_ai)
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._ai_soft_disabled = True

    assert await manager._reenable_ai_if_disabled() is False
    assert manager._ai_soft_disabled is True
    assert await manager._reenable_ai_if_disabled() is True

    assert manager._ai_soft_disabled is False
    assert local_calls == [True, True]
    assert camera.set_ai_enabled.await_count == 2


@pytest.mark.asyncio
async def test_viewer_wake_starts_capture_and_immediately_attempts_ai(monkeypatch):
    camera = SimpleNamespace(record_activity=Mock())
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._ensure_camera_running = AsyncMock(return_value=True)
    manager._reenable_ai_if_disabled = AsyncMock(return_value=False)

    assert await manager.wake_for_viewer() is True

    camera.record_activity.assert_called_once_with()
    manager._ensure_camera_running.assert_awaited_once_with()
    manager._reenable_ai_if_disabled.assert_awaited_once_with(force=True)


@pytest.mark.asyncio
async def test_owner_ai_command_ack_is_not_readiness_when_detector_failed(monkeypatch):
    local_ai = SimpleNamespace(
        ai_processing=SimpleNamespace(system_enabled=True),
        set_enabled=lambda _enabled: None,
    )
    camera = SimpleNamespace(
        ai_runtime_ready=False,
        hardware_fallback_active=False,
        requested_sim_mode=False,
        hardware_available=True,
        set_ai_enabled=AsyncMock(),
        get_camera_status=AsyncMock(return_value={"ai_runtime_ready": False}),
    )
    monkeypatch.setattr(ai_service_module, "get_ai_service", lambda: local_ai)
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._ai_soft_disabled = True

    assert await manager._reenable_ai_if_disabled(force=True) is False

    assert manager._ai_soft_disabled is True
    camera.set_ai_enabled.assert_awaited_once_with(True)
    camera.get_camera_status.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_owner_ai_reenable_requires_matching_model_identity(monkeypatch):
    expected_sha256 = "a" * 64

    class LocalAI:
        def __init__(self):
            self.ai_processing = SimpleNamespace(system_enabled=True)
            self.owner_model_sha256 = None

        def set_enabled(self, enabled):
            self.ai_processing.system_enabled = enabled

        def set_external_owner_state(self, **state):
            self.owner_model_sha256 = state["model_sha256"]

        async def get_ai_status(self):
            return {
                "system_enabled": self.ai_processing.system_enabled,
                "model_ready": self.owner_model_sha256 == expected_sha256,
            }

    local_ai = LocalAI()
    camera = SimpleNamespace(
        sim_mode=False,
        requested_sim_mode=False,
        hardware_available=True,
        hardware_fallback_active=False,
        ai_runtime_ready=True,
        ai_runtime_error=None,
        ai_model_sha256="b" * 64,
        set_ai_enabled=AsyncMock(),
        get_camera_status=AsyncMock(return_value={"ai_runtime_ready": True}),
    )
    monkeypatch.setattr(ai_service_module, "get_ai_service", lambda: local_ai)
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._ai_soft_disabled = True

    assert await manager._reenable_ai_if_disabled(force=True) is False
    assert manager._ai_soft_disabled is True

    camera.ai_model_sha256 = expected_sha256
    assert await manager._reenable_ai_if_disabled(force=True) is True
    assert manager._ai_soft_disabled is False


@pytest.mark.asyncio
async def test_idle_policy_refreshes_and_stops_restarted_camera_owner(monkeypatch):
    camera = SimpleNamespace(
        stream=SimpleNamespace(is_active=False),
        activity_age_seconds=lambda: power_manager_module.CAMERA_IDLE_TIMEOUT_S + 1.0,
        has_recent_activity=lambda _timeout: False,
    )

    async def refresh_status():
        camera.stream.is_active = True
        return {"is_active": True}

    async def stop_streaming():
        camera.stream.is_active = False

    camera.get_camera_status = AsyncMock(side_effect=refresh_status)
    camera.stop_streaming = AsyncMock(side_effect=stop_streaming)
    camera.start_streaming = AsyncMock(return_value=True)
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    manager = PowerManager()
    manager._camera_paused_by_pm = True
    manager._set_victron_rate = AsyncMock()
    manager._resume_gps_if_suspended = AsyncMock()
    manager._soft_disable_ai = AsyncMock()
    monkeypatch.setattr(manager, "_is_mission_active", lambda: False)
    monkeypatch.setattr(manager, "_is_moving", lambda: False)

    await manager._tick()

    camera.get_camera_status.assert_awaited_once_with()
    camera.stop_streaming.assert_awaited_once_with()
    assert camera.stream.is_active is False
    assert manager._camera_paused_by_pm is True
