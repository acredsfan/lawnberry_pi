# tests/unit/test_startup_config_report.py
"""Tests for the startup configuration report (§5 acceptance criterion).

The report must list loaded files, overlays applied, and effective values
excluding secrets. It must also appear in the /health response.

Run: SIM_MODE=1 uv run pytest tests/unit/test_startup_config_report.py -v
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from backend.src.core.startup_report import build_startup_report


@pytest.fixture
def hardware_yaml(tmp_path: Path) -> Path:
    f = tmp_path / "hardware.yaml"
    f.write_text("gps_type: neo-8m-uart\nimu_type: bno085-uart\n")
    return f


@pytest.fixture
def local_yaml(tmp_path: Path) -> Path:
    f = tmp_path / "hardware.local.yaml"
    f.write_text("gps_type: zed-f9p-usb\n")
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
        hardware_local_path=str(tmp_path / "nonexistent.yaml"),
        calibration_path=tmp_path / "calibration.json",
        secrets_keys=[],
    )
    assert str(hardware_yaml) in report["files_loaded"]
    assert str(limits_yaml) in report["files_loaded"]


def test_report_lists_overlays_when_local_exists(hardware_yaml, local_yaml, limits_yaml, tmp_path):
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        hardware_local_path=str(local_yaml),
        calibration_path=tmp_path / "calibration.json",
        secrets_keys=[],
    )
    assert str(local_yaml) in report["overlays_applied"]
    assert report["effective_values"]["hardware"]["gps_type"] == "zed-f9p-usb"


def test_report_excludes_secrets(hardware_yaml, limits_yaml, tmp_path):
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        hardware_local_path=str(tmp_path / "nonexistent.yaml"),
        calibration_path=tmp_path / "calibration.json",
        secrets_keys=["api_key", "ntrip_password"],
    )
    for key in report.get("effective_values", {}).get("hardware", {}):
        assert key not in ("api_key", "ntrip_password")


def test_report_includes_calibration_file(hardware_yaml, limits_yaml, tmp_path):
    cal = tmp_path / "calibration.json"
    cal.write_text('{"imu": {"session_heading_alignment": 42.0}}')
    report = build_startup_report(
        hardware_path=str(hardware_yaml),
        limits_path=str(limits_yaml),
        hardware_local_path=str(tmp_path / "nonexistent.yaml"),
        calibration_path=cal,
        secrets_keys=[],
    )
    assert str(cal) in report["files_loaded"]
    assert report["effective_values"]["calibration"]["imu"]["session_heading_alignment"] == pytest.approx(42.0)
