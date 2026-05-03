# tests/unit/test_calibration_repository.py
"""Unit tests for CalibrationRepository (JSON-backed).

Run: SIM_MODE=1 uv run pytest tests/unit/test_calibration_repository.py -v
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from backend.src.repositories.calibration_repository import CalibrationRepository


@pytest.fixture
def repo(tmp_path: Path) -> CalibrationRepository:
    return CalibrationRepository(calibration_path=tmp_path / "calibration.json")


def test_load_imu_alignment_default(repo: CalibrationRepository) -> None:
    """No file on disk returns the default 0.0."""
    alignment = repo.load_imu_alignment()
    assert alignment["session_heading_alignment"] == 0.0
    assert alignment["sample_count"] == 0


def test_save_and_load_imu_alignment(repo: CalibrationRepository) -> None:
    repo.save_imu_alignment(heading_deg=42.5, sample_count=12, source="gps_cog")
    alignment = repo.load_imu_alignment()
    assert alignment["session_heading_alignment"] == pytest.approx(42.5)
    assert alignment["sample_count"] == 12
    assert alignment["source"] == "gps_cog"


def test_imu_alignment_persists_to_file(repo: CalibrationRepository) -> None:
    repo.save_imu_alignment(heading_deg=180.0, sample_count=5, source="manual")
    raw = json.loads(repo._calibration_path.read_text())
    assert raw["imu"]["session_heading_alignment"] == pytest.approx(180.0)


def test_load_tunables_default(repo: CalibrationRepository) -> None:
    tunables = repo.load_tunables()
    assert isinstance(tunables, dict)


def test_save_and_load_tunables(repo: CalibrationRepository) -> None:
    repo.save_tunables({"waypoint_arrival_radius_m": 0.5, "max_speed_mps": 0.8})
    tunables = repo.load_tunables()
    assert tunables["waypoint_arrival_radius_m"] == pytest.approx(0.5)


def test_atomic_write_no_partial_file(repo: CalibrationRepository, monkeypatch) -> None:
    """If writing fails mid-way, the existing file is not corrupted."""
    repo.save_imu_alignment(heading_deg=10.0, sample_count=1, source="test")

    original_content = repo._calibration_path.read_text()

    def _fail_replace(dest):
        raise OSError("Simulated disk full")

    import pathlib
    monkeypatch.setattr(pathlib.Path, "replace", _fail_replace)

    # Should not raise, and existing file should be intact
    repo.save_imu_alignment(heading_deg=99.0, sample_count=2, source="corrupt_test")
    assert repo._calibration_path.read_text() == original_content
