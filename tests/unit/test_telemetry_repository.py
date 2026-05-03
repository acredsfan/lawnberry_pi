"""Unit tests for TelemetryRepository.

Run: SIM_MODE=1 uv run pytest tests/unit/test_telemetry_repository.py -v
"""
from __future__ import annotations

import pytest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from backend.src.repositories.telemetry_repository import TelemetryRepository


@pytest.fixture
def repo(tmp_path: Path) -> TelemetryRepository:
    return TelemetryRepository(db_path=tmp_path / "telemetry.db")


def _stream(component: str = "power") -> dict:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "component_id": component,
        "value": {"voltage": 12.5},
        "status": "healthy",
        "latency_ms": 1.0,
    }


def test_save_and_load_snapshot(repo: TelemetryRepository) -> None:
    repo.save_snapshot({"gps_lat": 40.0, "gps_lng": -75.0})
    snapshots = repo.list_snapshots(limit=10)
    assert len(snapshots) == 1
    assert snapshots[0]["data"]["gps_lat"] == pytest.approx(40.0)


def test_list_snapshots_empty(repo: TelemetryRepository) -> None:
    assert repo.list_snapshots() == []


def test_save_and_load_streams(repo: TelemetryRepository) -> None:
    now = datetime.now(UTC)
    s1 = _stream("power")
    s1["timestamp"] = (now - timedelta(seconds=1)).isoformat()
    s2 = _stream("imu")
    s2["timestamp"] = now.isoformat()
    repo.save_streams([s1, s2])
    streams = repo.list_streams(limit=10)
    assert len(streams) == 2
    component_ids = {s["component_id"] for s in streams}
    assert "power" in component_ids
    assert "imu" in component_ids


def test_list_streams_filter_by_component(repo: TelemetryRepository) -> None:
    now = datetime.now(UTC)
    s1 = _stream("power")
    s1["timestamp"] = (now - timedelta(seconds=1)).isoformat()
    s2 = _stream("gps")
    s2["timestamp"] = now.isoformat()
    repo.save_streams([s1, s2])
    power_only = repo.list_streams(component_id="power")
    assert all(s["component_id"] == "power" for s in power_only)


def test_cleanup_old_snapshots(repo: TelemetryRepository) -> None:
    repo.save_snapshot({"x": 1})
    deleted = repo.cleanup_snapshots(days_to_keep=0)
    assert deleted >= 1
    assert repo.list_snapshots() == []


def test_cleanup_old_streams(repo: TelemetryRepository) -> None:
    repo.save_streams([_stream()])
    deleted = repo.cleanup_streams(days_to_keep=0)
    assert deleted >= 1
    assert repo.list_streams() == []


def test_latency_stats(repo: TelemetryRepository) -> None:
    now = datetime.now(UTC)
    s1 = _stream("power")
    s1["timestamp"] = (now - timedelta(seconds=1)).isoformat()
    s2 = _stream("power")
    s2["timestamp"] = now.isoformat()
    repo.save_streams([s1, s2])
    stats = repo.compute_latency_stats(component_id="power")
    assert stats["count"] == 2
    assert stats["avg_latency_ms"] == pytest.approx(1.0)


def test_latency_stats_empty(repo: TelemetryRepository) -> None:
    stats = repo.compute_latency_stats()
    assert stats["count"] == 0
    assert stats["avg_latency_ms"] is None
    assert stats["min_latency_ms"] is None
    assert stats["max_latency_ms"] is None
