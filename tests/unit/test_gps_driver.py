from __future__ import annotations

import os

import pytest

from backend.src.drivers.sensors.gps_driver import GPSDriver
from backend.src.models.sensor_data import GpsMode


@pytest.mark.asyncio
async def test_gps_driver_sim_mode_produces_positions():
    os.environ["SIM_MODE"] = "1"
    drv = GPSDriver({"mode": GpsMode.F9P_USB.value})
    await drv.initialize()
    await drv.start()

    r1 = await drv.read_position()
    r2 = await drv.read_position()
    assert r1 is not None and r2 is not None
    assert r1.latitude is not None and r1.longitude is not None
    # Accuracy should be < 1m for F9P in SIM
    assert r1.accuracy is not None and r1.accuracy < 1.5
    # Subsequent reads should move slightly
    assert r2.latitude != r1.latitude or r2.longitude != r1.longitude


@pytest.mark.asyncio
async def test_gps_driver_health_check_fields():
    os.environ["SIM_MODE"] = "1"
    drv = GPSDriver({"mode": GpsMode.NEO8M_UART.value})
    await drv.initialize()
    await drv.start()
    await drv.read_position()
    hc = await drv.health_check()
    assert hc["driver"] == "gps"
    assert hc["mode"] in {GpsMode.NEO8M_UART.value, GpsMode.F9P_USB.value}
    assert hc["initialized"] is True
    assert hc["running"] is True
