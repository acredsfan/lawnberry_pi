"""Tests for velocity field IMU wiring."""
import pytest
from unittest.mock import MagicMock


def _get_velocity(imu_gyro_x=0.1, imu_gyro_y=0.2):
    from backend.src.services.telemetry_service import TelemetryService
    svc = TelemetryService()
    svc._get_navigation_heading = lambda: None

    imu = MagicMock()
    imu.gyro_x = imu_gyro_x
    imu.gyro_y = imu_gyro_y
    imu.gyro_z = 0.03
    imu.yaw = 0.0
    imu.roll = 0.0
    imu.pitch = 0.0
    imu.calibration_status = "uncalibrated"

    data = MagicMock()
    data.imu = imu
    data.gps = None
    data.power = None
    data.tof_left = None
    data.tof_right = None
    data.environmental = None

    result = svc._format_telemetry(data, sim_mode=True)
    return result["velocity"]


def test_velocity_linear_y_is_zero():
    vel = _get_velocity()
    assert vel["linear"]["y"] == 0.0


def test_velocity_linear_z_is_zero():
    vel = _get_velocity()
    assert vel["linear"]["z"] == 0.0


def test_velocity_angular_x_from_imu():
    vel = _get_velocity(imu_gyro_x=0.1)
    assert vel["angular"]["x"] == pytest.approx(0.1)


def test_velocity_angular_y_from_imu():
    vel = _get_velocity(imu_gyro_y=0.2)
    assert vel["angular"]["y"] == pytest.approx(0.2)


def test_velocity_angular_z_from_imu():
    """gyro_z should still be wired."""
    from backend.src.services.telemetry_service import TelemetryService
    svc = TelemetryService()
    svc._get_navigation_heading = lambda: None

    imu = MagicMock()
    imu.gyro_x = 0.0
    imu.gyro_y = 0.0
    imu.gyro_z = 0.05
    imu.yaw = 0.0
    imu.roll = 0.0
    imu.pitch = 0.0
    imu.calibration_status = "uncalibrated"

    data = MagicMock()
    data.imu = imu
    data.gps = None
    data.power = None
    data.tof_left = None
    data.tof_right = None
    data.environmental = None

    result = svc._format_telemetry(data, sim_mode=True)
    assert result["velocity"]["angular"]["z"] == pytest.approx(0.05)


def test_velocity_linear_x_from_speed():
    """linear.x should come from GPS speed."""
    from backend.src.services.telemetry_service import TelemetryService
    svc = TelemetryService()
    svc._get_navigation_heading = lambda: None

    imu = MagicMock()
    imu.gyro_x = 0.0
    imu.gyro_y = 0.0
    imu.gyro_z = 0.0
    imu.yaw = 0.0
    imu.roll = 0.0
    imu.pitch = 0.0
    imu.calibration_status = "uncalibrated"

    gps = MagicMock()
    gps.speed = 1.5
    gps.latitude = None
    gps.longitude = None
    gps.altitude = None
    gps.accuracy = None
    gps.mode = None
    gps.satellites = None
    gps.heading = None
    gps.rtk_status = None
    gps.hdop = None

    data = MagicMock()
    data.imu = imu
    data.gps = gps
    data.power = None
    data.tof_left = None
    data.tof_right = None
    data.environmental = None

    result = svc._format_telemetry(data, sim_mode=True)
    assert result["velocity"]["linear"]["x"] == pytest.approx(1.5)
