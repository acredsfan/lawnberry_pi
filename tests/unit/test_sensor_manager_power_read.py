"""Tests for PowerSensorInterface.read_power parallel driver behaviour."""

import asyncio
import math
import pytest
from unittest.mock import AsyncMock

from backend.src.services.sensor_manager import PowerSensorInterface, SensorStatus
from backend.src.models.sensor_data import PowerReading


def _make_psi(ina_driver=None, victron_driver=None, last_reading=None):
    """Build a PowerSensorInterface without triggering hardware imports."""
    psi = PowerSensorInterface.__new__(PowerSensorInterface)
    psi.status = SensorStatus.ONLINE
    psi._ina_driver = ina_driver
    psi._victron_driver = victron_driver
    psi._prefer_battery = False
    psi._prefer_solar = False
    psi._prefer_load = False
    psi.last_reading = last_reading
    psi._battery_consumed_today_wh = 0.0
    psi._solar_yield_today_wh = 0.0
    psi._last_power_read_dt = None
    psi._last_accumulation_date = None
    return psi


@pytest.mark.asyncio
async def test_read_power_parallel_ina_succeeds_victron_stalls():
    """INA3221 data surfaces even when Victron BLE stalls past its 4 s budget."""

    async def _stall():
        await asyncio.sleep(10)  # exceeds VICTRON_TIMEOUT_S=4 — will be cancelled

    ina = AsyncMock()
    ina.read_power = AsyncMock(return_value={"battery_voltage": 12.5, "battery_current": 2.0})
    victron = AsyncMock()
    victron.read_power = AsyncMock(side_effect=_stall)

    psi = _make_psi(ina_driver=ina, victron_driver=victron)

    # Must complete well within the outer 5 s budget (Victron timeout = 4 s + margin)
    reading = await asyncio.wait_for(psi.read_power(), timeout=5.5)

    assert reading is not None, "Expected a PowerReading, got None"
    assert math.isclose(reading.battery_voltage, 12.5, rel_tol=1e-6)
    assert math.isclose(reading.battery_current, 2.0, rel_tol=1e-6)
    # Victron solar fields should be absent
    assert reading.solar_voltage is None


@pytest.mark.asyncio
async def test_read_power_both_stall_returns_none_when_no_last_reading():
    """Both drivers timing out returns None when there is no previous reading."""

    async def _stall():
        await asyncio.sleep(10)

    ina = AsyncMock()
    ina.read_power = AsyncMock(side_effect=_stall)
    victron = AsyncMock()
    victron.read_power = AsyncMock(side_effect=_stall)

    psi = _make_psi(ina_driver=ina, victron_driver=victron)

    reading = await asyncio.wait_for(psi.read_power(), timeout=5.5)

    # No last_reading to fall back to — should return None
    assert reading is None


@pytest.mark.asyncio
async def test_read_power_both_stall_returns_last_reading_when_available():
    """Both drivers timing out still returns the previous cached reading."""

    async def _stall():
        await asyncio.sleep(10)

    ina = AsyncMock()
    ina.read_power = AsyncMock(side_effect=_stall)
    victron = AsyncMock()
    victron.read_power = AsyncMock(side_effect=_stall)

    prev = PowerReading(battery_voltage=11.9, battery_current=1.5)
    psi = _make_psi(ina_driver=ina, victron_driver=victron, last_reading=prev)

    reading = await asyncio.wait_for(psi.read_power(), timeout=5.5)

    # Falls back to last_reading
    assert reading is not None
    assert math.isclose(reading.battery_voltage, 11.9, rel_tol=1e-6)


@pytest.mark.asyncio
async def test_read_power_ina_only_no_victron():
    """Works correctly with only an INA3221 driver (no Victron configured)."""
    ina = AsyncMock()
    ina.read_power = AsyncMock(return_value={"battery_voltage": 13.1, "load_current_amps": 0.8})

    psi = _make_psi(ina_driver=ina, victron_driver=None)

    reading = await asyncio.wait_for(psi.read_power(), timeout=2.0)

    assert reading is not None
    assert math.isclose(reading.battery_voltage, 13.1, rel_tol=1e-6)


@pytest.mark.asyncio
async def test_read_power_returns_none_when_offline():
    """Returns None immediately when the sensor is not ONLINE."""
    psi = _make_psi()
    psi.status = SensorStatus.OFFLINE

    reading = await psi.read_power()

    assert reading is None
