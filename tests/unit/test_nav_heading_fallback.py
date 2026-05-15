"""Tests for nav_heading fallback to IMU yaw."""
import pytest
from unittest.mock import MagicMock, patch


def _make_service():
    from backend.src.services.telemetry_service import TelemetryService
    svc = TelemetryService()
    return svc


def _make_sensor_data(imu_yaw=172.6, imu_cal="fully_calibrated", power=None):
    imu = MagicMock()
    imu.yaw = imu_yaw
    imu.calibration_status = imu_cal
    imu.roll = 0.0
    imu.pitch = 0.0
    imu.gyro_z = 0.0
    imu.gyro_x = 0.0
    imu.gyro_y = 0.0
    data = MagicMock()
    data.imu = imu
    data.gps = None
    data.power = power
    data.tof_left = None
    data.tof_right = None
    data.environmental = None
    return data


def test_nav_heading_falls_back_to_imu_when_localization_none(monkeypatch):
    """When localization returns None, IMU yaw is used for nav_heading."""
    svc = _make_service()
    monkeypatch.setattr(svc, "_get_navigation_heading", lambda: None)
    data = _make_sensor_data(imu_yaw=172.6, imu_cal="fully_calibrated")
    result = svc._format_telemetry(data, sim_mode=False)
    assert result["nav_heading"] is not None, "Should fall back to IMU yaw"
    assert result["nav_heading_source"] == "imu_raw"


def test_nav_heading_uses_localization_when_available(monkeypatch):
    svc = _make_service()
    monkeypatch.setattr(svc, "_get_navigation_heading", lambda: 45.0)
    data = _make_sensor_data()
    result = svc._format_telemetry(data, sim_mode=False)
    assert result["nav_heading"] == pytest.approx(45.0)
    assert result["nav_heading_source"] == "localization"


def test_nav_heading_not_fallback_when_uncalibrated(monkeypatch):
    """Uncalibrated IMU should NOT be used as fallback."""
    svc = _make_service()
    monkeypatch.setattr(svc, "_get_navigation_heading", lambda: None)
    data = _make_sensor_data(imu_cal="uncalibrated")
    result = svc._format_telemetry(data, sim_mode=False)
    assert result["nav_heading"] is None


def test_nav_heading_source_present_in_telemetry(monkeypatch):
    """nav_heading_source key must always be present in telemetry dict."""
    svc = _make_service()
    monkeypatch.setattr(svc, "_get_navigation_heading", lambda: 90.0)
    data = _make_sensor_data()
    result = svc._format_telemetry(data, sim_mode=True)
    assert "nav_heading_source" in result


def test_nav_heading_fallback_calibrated_alias(monkeypatch):
    """'calibrated' status (not just 'fully_calibrated') should also allow fallback."""
    svc = _make_service()
    monkeypatch.setattr(svc, "_get_navigation_heading", lambda: None)
    data = _make_sensor_data(imu_yaw=55.0, imu_cal="calibrated")
    result = svc._format_telemetry(data, sim_mode=False)
    assert result["nav_heading"] is not None
    assert result["nav_heading_source"] == "imu_raw"
