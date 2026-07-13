# tests/unit/test_calibration_repository.py
"""Unit tests for CalibrationRepository (JSON-backed).

Run: SIM_MODE=1 uv run pytest tests/unit/test_calibration_repository.py -v
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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


def test_newer_authoritative_legacy_alignment_replaces_reset_canonical(tmp_path: Path) -> None:
    canonical = tmp_path / "calibration.json"
    legacy = tmp_path / "imu_alignment.json"
    canonical.write_text(
        json.dumps(
            {
                "imu": {
                    "session_heading_alignment": 0.0,
                    "sample_count": 0,
                    "source": "mission_start_reset",
                    "last_updated": "2026-06-20T16:37:49+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": 90.0,
                "sample_count": 1,
                "source": "gps_cog_snap",
                "last_updated": "2026-07-13T15:09:39+00:00",
            }
        ),
        encoding="utf-8",
    )

    repository = CalibrationRepository(calibration_path=canonical)

    alignment = repository.load_imu_alignment()
    assert alignment == {
        "session_heading_alignment": 90.0,
        "sample_count": 1,
        "source": "gps_cog_snap",
        "last_updated": "2026-07-13T15:09:39+00:00",
    }
    assert legacy.exists() is False
    assert legacy.with_suffix(".json.migrated").exists() is True


def test_newer_valid_canonical_alignment_wins_over_legacy(tmp_path: Path) -> None:
    canonical = tmp_path / "calibration.json"
    legacy = tmp_path / "imu_alignment.json"
    canonical.write_text(
        json.dumps(
            {
                "imu": {
                    "session_heading_alignment": 45.0,
                    "sample_count": 2,
                    "source": "gps_cog_snap",
                    "last_updated": "2026-07-13T16:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": 90.0,
                "sample_count": 1,
                "source": "gps_cog_snap",
                "last_updated": "2026-07-13T15:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    alignment = CalibrationRepository(calibration_path=canonical).load_imu_alignment()

    assert alignment["session_heading_alignment"] == pytest.approx(45.0)
    assert alignment["sample_count"] == 2
    assert alignment["last_updated"] == "2026-07-13T16:00:00+00:00"


def test_newer_reset_canonical_blocks_older_legacy_alignment(tmp_path: Path) -> None:
    canonical = tmp_path / "calibration.json"
    legacy = tmp_path / "imu_alignment.json"
    canonical.write_text(
        json.dumps(
            {
                "imu": {
                    "session_heading_alignment": 0.0,
                    "sample_count": 0,
                    "source": "mission_start_reset",
                    "last_updated": "2026-07-13T16:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": 90.0,
                "sample_count": 1,
                "source": "gps_cog_snap",
                "last_updated": "2026-07-13T15:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    alignment = CalibrationRepository(calibration_path=canonical).load_imu_alignment()

    assert alignment["sample_count"] == 0
    assert alignment["source"] == "mission_start_reset"


@pytest.mark.parametrize("source", ["mission_start_reset", "gps_cog_snap_fallback"])
def test_non_authoritative_legacy_alignment_is_ignored(tmp_path: Path, source: str) -> None:
    canonical = tmp_path / "calibration.json"
    legacy = tmp_path / "imu_alignment.json"
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": 90.0,
                "sample_count": 1,
                "source": source,
                "last_updated": "2026-07-13T15:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    alignment = CalibrationRepository(calibration_path=canonical).load_imu_alignment()

    assert alignment["sample_count"] == 0
    assert alignment["source"] == "default"


@pytest.mark.parametrize("source", ["", "manual", "unknown_source"])
def test_unknown_legacy_alignment_source_is_ignored(tmp_path: Path, source: str) -> None:
    legacy = tmp_path / "imu_alignment.json"
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": 90.0,
                "sample_count": 1,
                "source": source,
                "last_updated": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    alignment = CalibrationRepository(
        calibration_path=tmp_path / "calibration.json"
    ).load_imu_alignment()

    assert alignment["sample_count"] == 0


def test_non_finite_legacy_alignment_is_ignored(tmp_path: Path) -> None:
    legacy = tmp_path / "imu_alignment.json"
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": math.nan,
                "sample_count": 1,
                "source": "gps_cog_snap",
                "last_updated": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    alignment = CalibrationRepository(
        calibration_path=tmp_path / "calibration.json"
    ).load_imu_alignment()

    assert alignment["sample_count"] == 0


def test_future_legacy_alignment_is_ignored(tmp_path: Path) -> None:
    legacy = tmp_path / "imu_alignment.json"
    legacy.write_text(
        json.dumps(
            {
                "session_heading_alignment": 90.0,
                "sample_count": 1,
                "source": "gps_cog_snap",
                "last_updated": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    alignment = CalibrationRepository(
        calibration_path=tmp_path / "calibration.json"
    ).load_imu_alignment()

    assert alignment["sample_count"] == 0


def test_reusable_alignment_must_match_current_imu_epoch(tmp_path: Path) -> None:
    canonical = tmp_path / "calibration.json"
    first = CalibrationRepository(calibration_path=canonical, imu_epoch_id="epoch-a")
    first.save_imu_alignment(
        heading_deg=42.0,
        sample_count=1,
        source="gps_cog_snap",
        imu_epoch_id="epoch-a",
    )

    assert first.load_reusable_imu_alignment(max_age_s=3600) is not None

    restarted = CalibrationRepository(calibration_path=canonical, imu_epoch_id="epoch-b")
    assert restarted.load_reusable_imu_alignment(max_age_s=3600) is None


def test_reinitialized_imu_cannot_rebind_old_alignment_as_current(tmp_path: Path) -> None:
    canonical = tmp_path / "calibration.json"
    repository = CalibrationRepository(calibration_path=canonical, imu_epoch_id="epoch-a")
    assert repository.save_imu_alignment(
        heading_deg=42.0,
        sample_count=3,
        source="gps_cog_snap",
        imu_epoch_id="epoch-a",
    )

    assert repository.bind_imu_epoch("epoch-b") is True
    assert repository.save_imu_alignment(
        heading_deg=42.0,
        sample_count=12,
        source="stop_navigation",
        imu_epoch_id="epoch-a",
    ) is False
    assert repository.load_reusable_imu_alignment(max_age_s=3600) is None
    assert json.loads(canonical.read_text())["imu"]["imu_epoch_id"] == "epoch-a"
