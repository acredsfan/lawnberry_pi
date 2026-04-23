import math
import asyncio
import pytest

from backend.src.drivers.sensors.victron_vedirect import VictronVeDirectDriver
from backend.src.services.sensor_manager import PowerSensorInterface


def test_merge_prefers_victron_battery_current_when_requested():
    ina_payload = {"battery_current": 3.0, "battery_voltage": 12.8}
    victron_payload = {"battery_current_amps": 1.2, "battery_voltage": 12.6}

    reading = PowerSensorInterface._merge_power_payload(
        ina_payload,
        victron_payload,
        prefer_battery=True,
    )

    assert reading is not None
    assert math.isclose(reading.battery_current, 1.2, rel_tol=1e-6)
    assert math.isclose(reading.battery_voltage, 12.6, rel_tol=1e-6)


def test_merge_prefers_ina_battery_current_by_default():
    ina_payload = {"battery_current": 2.5, "battery_voltage": 12.7}
    victron_payload = {"battery_current_amps": 1.1, "battery_voltage": 12.6}

    reading = PowerSensorInterface._merge_power_payload(ina_payload, victron_payload)

    assert reading is not None
    assert math.isclose(reading.battery_current, 2.5, rel_tol=1e-6)


def test_merge_prefers_victron_load_when_enabled():
    ina_payload = {"load_current_amps": 0.2}
    victron_payload = {"load_current_amps": 0.6}

    default_reading = PowerSensorInterface._merge_power_payload(ina_payload, victron_payload)
    preferred_reading = PowerSensorInterface._merge_power_payload(
        ina_payload,
        victron_payload,
        prefer_load=True,
    )

    assert default_reading is not None
    assert math.isclose(default_reading.load_current, 0.2, rel_tol=1e-6)
    assert preferred_reading is not None
    assert math.isclose(preferred_reading.load_current, 0.6, rel_tol=1e-6)


def test_convert_frame_handles_ble_payload():
    frame = {
        "name": "SmartSolar",
        "address": "EC:1A:A8:DD:99:C2",
        "payload": {
            "battery_voltage": 13.5,
            "battery_charging_current": 0.7,
            "solar_power": 15.0,
            "external_device_load": 0.4,
            "charge_state": "float",
        },
    }

    converted = VictronVeDirectDriver._convert_frame(frame)

    assert converted is not None
    assert math.isclose(converted["battery_voltage"], 13.5, rel_tol=1e-6)
    assert math.isclose(converted["battery_current_amps"], 0.7, rel_tol=1e-6)
    assert math.isclose(converted["solar_power_w"], 15.0, rel_tol=1e-6)
    assert math.isclose(converted["load_current_amps"], 0.4, rel_tol=1e-6)
    assert converted.get("meta", {}).get("charge_state") == "float"


# ── VictronVeDirectDriver non-blocking read_power tests ─────────────────────


@pytest.fixture()
def non_sim_victron(monkeypatch):
    """VictronVeDirectDriver configured to behave as if SIM_MODE is off.

    Also stubs out _read_victron_cli_frame so no real BLE subprocess is launched.
    """
    monkeypatch.setenv("SIM_MODE", "0")

    drv = VictronVeDirectDriver({"enabled": True, "bg_refresh_interval_s": 30.0})
    # Stub the blocking BLE subprocess so background tasks complete cleanly.
    drv._read_victron_cli_frame = lambda: None
    return drv


@pytest.mark.asyncio
async def test_read_power_returns_cache_immediately_when_fresh(non_sim_victron):
    """read_power() must return cached data without blocking when cache is fresh."""
    import time as _time

    drv = non_sim_victron
    await drv.initialize()
    payload = {"battery_voltage": 12.8, "battery_current_amps": 1.5}
    drv._last_payload = payload
    drv._last_timestamp = _time.time()  # just set — definitely fresh

    result = await drv.read_power()

    assert result is payload
    # No background task should have been scheduled since cache is fresh.
    assert drv._refresh_task is None


@pytest.mark.asyncio
async def test_read_power_schedules_bg_refresh_when_cache_stale(non_sim_victron):
    """read_power() must schedule a background task when cache is stale/empty."""
    import time as _time

    drv = non_sim_victron
    drv._bg_refresh_interval_s = 0.001
    await drv.initialize()
    old_payload = {"battery_voltage": 12.1}
    drv._last_payload = old_payload
    drv._last_timestamp = _time.time() - 99.0  # definitely stale

    result = await drv.read_power()

    # Must return cached data immediately (not block waiting for BLE).
    assert result is old_payload
    # A background refresh task must have been scheduled.
    assert drv._refresh_task is not None
    # Allow the task to complete (stubbed frame reader returns None quickly).
    await asyncio.gather(drv._refresh_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_read_power_returns_none_when_no_cache(non_sim_victron):
    """With no cache at all read_power() returns None and schedules refresh."""
    drv = non_sim_victron
    drv._bg_refresh_interval_s = 60.0
    await drv.initialize()
    # No cache set.

    result = await drv.read_power()

    assert result is None
    # A background refresh must have been scheduled.
    assert drv._refresh_task is not None
    await asyncio.gather(drv._refresh_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_read_power_does_not_duplicate_refresh_task(non_sim_victron):
    """A second call while a refresh is in flight must not schedule another task."""
    import time as _time

    drv = non_sim_victron
    drv._bg_refresh_interval_s = 0.001
    await drv.initialize()
    drv._last_payload = {"battery_voltage": 12.0}
    drv._last_timestamp = _time.time() - 99.0  # stale

    # First call — schedules refresh task.
    await drv.read_power()
    first_task = drv._refresh_task
    assert first_task is not None

    # Second call — task is still running, must reuse it.
    await drv.read_power()
    assert drv._refresh_task is first_task

    await asyncio.gather(first_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_stop_cancels_pending_refresh_task(non_sim_victron):
    """stop() must cancel an in-flight refresh task cleanly."""
    import time as _time

    drv = non_sim_victron
    drv._bg_refresh_interval_s = 0.001
    await drv.initialize()
    drv._last_payload = {"battery_voltage": 12.0}
    drv._last_timestamp = _time.time() - 99.0

    await drv.read_power()
    assert drv._refresh_task is not None

    await drv.stop()
    assert drv._refresh_task is None
