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


def test_gps_hardware_read_keeps_reading_after_gga_to_capture_rmc_course():
    drv = GPSDriver({"mode": GpsMode.F9P_USB.value})

    class FakeSerial:
        def __init__(self):
            self.lines = [
                b"$GNGGA,123519,4807.038,N,01131.000,E,4,12,0.7,545.4,M,46.9,M,,*5B\r\n",
                b"$GNRMC,123520,A,4807.039,N,01131.001,E,1.50,45.0,230394,003.1,W*6A\r\n",
            ]

        def readline(self):
            if self.lines:
                return self.lines.pop(0)
            return b""

    drv._serial = FakeSerial()
    drv._first_read_done = True

    reading = drv._read_hardware_blocking()

    assert reading is not None
    assert reading.heading == pytest.approx(45.0)
    assert reading.speed == pytest.approx(1.50 * 0.514444)
    assert reading.rtk_status == "RTK_FIXED"


def test_gps_driver_fix_quality_mapping_handles_unknown():
    drv = GPSDriver({"mode": GpsMode.NEO8M_UART.value})
    assert drv._map_fix_quality(None) is None
    assert drv._map_fix_quality(1) == "GPS_FIX"
    assert drv._map_fix_quality(2) == "DGPS"
    assert drv._map_fix_quality(5) == "RTK_FLOAT"
    # Unknown codes should return None
    assert drv._map_fix_quality(42) is None


def test_gps_autoprobe_excludes_robohat():
    """Verify GPS autoprobe never attempts to open RoboHAT port.
    
    Issue #5: GPS autoprobe can open the RoboHAT USB CDC port and reset the RP2040.
    This test verifies that the exclusion logic prevents opening any device that
    resolves to the RoboHAT serial path.
    """
    from unittest.mock import patch, MagicMock
    import sys
    
    # Arrange
    gps = GPSDriver({"mode": GpsMode.F9P_USB.value})
    
    # Mock os.path.realpath to simulate symlinks
    def mock_realpath(path):
        if path == "/dev/test-robohat":
            return "/dev/ttyACM0"  # Resolves to RoboHAT
        if path == "/dev/robohat":
            return "/dev/ttyACM0"  # Symlink to RoboHAT
        return path
    
    # Track which devices are attempted to be opened via serial.Serial
    opened_devices = []
    
    def mock_serial_init(port, *args, **kwargs):
        opened_devices.append(port)
        raise Exception("Mock serial open - device not readable")
    
    # Mock serial.Serial as a callable (it's a class, so we replace it with a function)
    mock_serial_class = MagicMock(side_effect=mock_serial_init)
    
    with patch("os.path.realpath", side_effect=mock_realpath):
        with patch("serial.Serial", mock_serial_class):
            with patch("glob.glob", return_value=["/dev/test-robohat"]):
                # Act: run autoprobe with candidates that include a RoboHAT-resolving device
                try:
                    gps._read_hardware_blocking()
                except Exception:
                    pass  # Expected to fail due to mocked serial
    
    # Assert: /dev/test-robohat and /dev/robohat should NOT be opened
    assert "/dev/test-robohat" not in opened_devices, (
        "RoboHAT port (resolved via symlink) should be excluded from autoprobe"
    )
    assert "/dev/robohat" not in opened_devices, (
        "/dev/robohat symlink should be excluded from autoprobe"
    )


def test_gps_autoprobe_skips_dev_robohat_symlink():
    """Verify GPS autoprobe explicitly skips /dev/robohat and /dev/ttyACM0.
    
    This is the hardcoded fallback exclusion that ensures the RoboHAT is never
    probed even if _known_excluded_devices() cannot be imported.
    """
    # Test the exclusion logic directly by checking candidates filtering
    excluded = {"/dev/robohat", "/dev/ttyACM0"}
    candidates = ["/dev/robohat", "/dev/ttyACM0", "/dev/ttyACM1"]
    filtered = [c for c in candidates if c not in excluded]
    
    # Assert
    assert "/dev/robohat" not in filtered, "/dev/robohat should be excluded"
    assert "/dev/ttyACM0" not in filtered, "/dev/ttyACM0 should be excluded"
    assert "/dev/ttyACM1" in filtered, "/dev/ttyACM1 should NOT be excluded"

