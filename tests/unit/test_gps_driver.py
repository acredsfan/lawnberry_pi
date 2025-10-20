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


def test_gps_driver_parse_gga_and_fix_quality():
    drv = GPSDriver({"mode": GpsMode.F9P_USB.value})
    sentence = (
        "$GNGGA,123519,4807.038,N,01131.000,E,4,12,0.7,545.4,M,46.9,M,,*5B"
    )
    parsed = drv._parse_gga(sentence)
    assert parsed is not None
    lat, lon, alt, sats, hdop, fix_quality = parsed
    assert lat == pytest.approx(48.1173, rel=1e-4)
    assert lon == pytest.approx(11.5166667, rel=1e-4)
    assert alt == pytest.approx(545.4)
    assert sats == 12
    assert hdop == pytest.approx(0.7)
    assert fix_quality == 4
    # Fix quality 4 should map to RTK fixed status
    status = drv._map_fix_quality(fix_quality)
    assert status == "RTK_FIXED"


def test_gps_driver_parse_gst_accuracy():
    drv = GPSDriver({"mode": GpsMode.F9P_USB.value})
    # SD values 0.02 m and 0.03 m should combine via sqrt(a^2 + b^2)
    gst = "$GPGST,024603.00,0.010,0.020,0.030,0.000,0.020,0.030,0.050*5C"
    accuracy = drv._parse_gst(gst)
    assert accuracy == pytest.approx((0.02 ** 2 + 0.03 ** 2) ** 0.5)


def test_gps_driver_fix_quality_mapping_handles_unknown():
    drv = GPSDriver({"mode": GpsMode.NEO8M_UART.value})
    assert drv._map_fix_quality(None) is None
    assert drv._map_fix_quality(1) == "GPS_FIX"
    assert drv._map_fix_quality(2) == "DGPS"
    assert drv._map_fix_quality(5) == "RTK_FLOAT"
    # Unknown codes should return None
    assert drv._map_fix_quality(42) is None
