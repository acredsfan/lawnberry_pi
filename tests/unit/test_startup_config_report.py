# tests/unit/test_startup_config_report.py
"""Tests for the startup configuration report (§5 acceptance criterion).

The report must list loaded files, one hardware source, and redacted effective
values. It must also appear in the /health response.

Run: SIM_MODE=1 uv run pytest tests/unit/test_startup_config_report.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.core.startup_report import build_startup_report
from backend.src.models.hardware_config import HardwareConfig
from backend.src.models.safety_limits import SafetyLimits


@pytest.fixture
def hardware_yaml(tmp_path: Path) -> Path:
    f = tmp_path / "hardware.yaml"
    f.write_text("gps_type: neo-8m-uart\nimu_type: bno085-uart\n")
    return f


@pytest.fixture
def limits_yaml(tmp_path: Path) -> Path:
    f = tmp_path / "limits.yaml"
    f.write_text("max_speed_mps: 1.2\ngeofence_buffer_m: 0.5\n")
    return f


def test_report_lists_loaded_files(hardware_yaml, limits_yaml, tmp_path):
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        calibration_path=tmp_path / "calibration.json",
        secrets_keys=[],
        hardware_config=HardwareConfig(gps_type="neo-8m-uart", imu_type="bno085-uart"),
        safety_limits=SafetyLimits(),
        source_metadata={"hardware_source": str(hardware_yaml), "hardware_loaded": True},
    )
    assert str(hardware_yaml) in report["files_loaded"]
    assert str(limits_yaml) in report["files_loaded"]
    assert report["hardware_source"] == str(hardware_yaml)
    assert report["hardware_loaded"] is True
    assert report["hardware_overlay"] is None


def test_report_does_not_apply_hardware_overlays(hardware_yaml, limits_yaml, tmp_path):
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        calibration_path=tmp_path / "calibration.json",
        secrets_keys=[],
        hardware_config=HardwareConfig(gps_type="neo-8m-uart", imu_type="bno085-uart"),
        safety_limits=SafetyLimits(),
        source_metadata={"hardware_source": str(hardware_yaml), "hardware_loaded": True},
    )
    assert report["overlays_applied"] == []
    assert report["effective_values"]["hardware"]["gps_type"] == "neo-8m-uart"


def test_report_excludes_secrets(hardware_yaml, limits_yaml, tmp_path):
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        calibration_path=tmp_path / "calibration.json",
        secrets_keys=["api_key", "ntrip_password", "device_key"],
        hardware_config=HardwareConfig(
            gps_type="neo-8m-uart",
            imu_type="bno085-uart",
            victron_config={
                "enabled": True,
                "device_key": "combined-secret",
                "encryption_key": "secret-key",
            },
        ),
        safety_limits=SafetyLimits(),
        source_metadata={"hardware_source": str(hardware_yaml), "hardware_loaded": True},
    )
    victron = report["effective_values"]["hardware"]["victron_config"]
    assert victron["device_key"] == "[REDACTED]"
    assert victron["encryption_key"] == "[REDACTED]"
    assert "combined-secret" not in str(report)
    assert "secret-key" not in str(report)


def test_report_includes_calibration_file(hardware_yaml, limits_yaml, tmp_path):
    cal = tmp_path / "calibration.json"
    cal.write_text('{"imu": {"session_heading_alignment": 42.0}}')
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        calibration_path=cal,
        secrets_keys=[],
        hardware_config=HardwareConfig(gps_type="neo-8m-uart", imu_type="bno085-uart"),
        safety_limits=SafetyLimits(),
        source_metadata={"hardware_source": str(hardware_yaml), "hardware_loaded": True},
    )
    assert str(cal) in report["files_loaded"]
    assert report["effective_values"]["calibration"]["imu"]["session_heading_alignment"] == pytest.approx(42.0)
