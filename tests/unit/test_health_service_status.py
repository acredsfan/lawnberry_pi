import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from backend.src.core.health import HealthService
from backend.src.core.observability import observability


@pytest.fixture(autouse=True)
def _reset_observability():
    observability.reset_events_for_testing()
    yield
    observability.reset_events_for_testing()


def _write_hardware_config(path: Path) -> None:
    payload = {
        "gps": {"type": "ZED-F9P"},
        "imu": {"type": "BNO085"},
        "sensors": {"tof": ["left", "right"]},
        "power_monitor": True,
        "motor_controller": "robohat-rp2040",
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))


def _write_system_config(path: Path, *, remote_access: bool) -> None:
    payload = {"system": {"remote_access": remote_access}}
    path.write_text(json.dumps(payload))


def _initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 1")


def _fake_sensor_health(status: str = "healthy") -> dict[str, Any]:
    return {
        "status": status,
        "detail": "simulated",
        "components": {"gps": {"status": status, "health": status}},
        "initialized": True,
        "last_checked": datetime.now(UTC).isoformat(),
    }


def _fake_dependencies(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "metrics_collector": {"status": "healthy", "detail": "simulated"},
        "log_storage": {"status": "healthy", "detail": "simulated"},
    }


def test_health_service_reports_critical_without_hardware_config(tmp_path: Path):
    service = HealthService(
        hardware_config_path=tmp_path / "missing.yaml",
        system_config_path=tmp_path / "default.json",
        remote_access_status_path=tmp_path / "remote_access_status.json",
        database_path=tmp_path / "lawnberry.db",
        error_window_seconds=60,
        sensor_health_provider=_fake_sensor_health,
        dependency_provider=_fake_dependencies,
    )

    report = service.evaluate()

    assert report["hardware"]["status"] == "critical"
    assert report["overall_status"] == "critical"
    assert report["sensor_health"]["status"] == "healthy"
    assert report["dependencies"]["metrics_collector"]["status"] == "healthy"


def test_health_service_captures_recent_errors(tmp_path: Path):
    hardware_path = tmp_path / "hardware.yaml"
    system_path = tmp_path / "default.json"
    db_path = tmp_path / "lawnberry.db"

    _write_hardware_config(hardware_path)
    _write_system_config(system_path, remote_access=False)
    _initialize_database(db_path)

    service = HealthService(
        hardware_config_path=hardware_path,
        system_config_path=system_path,
        remote_access_status_path=tmp_path / "remote_access_status.json",
        database_path=db_path,
        error_window_seconds=300,
        sensor_health_provider=_fake_sensor_health,
        dependency_provider=_fake_dependencies,
    )

    observability.record_error(origin="http_request", message="api failure")
    observability.record_error(origin="job_scheduler", message="job failure")

    report = service.evaluate()
    subsystems = report["subsystems"]

    assert subsystems["api"]["status"] == "degraded"
    assert subsystems["job_scheduler"]["status"] == "degraded"
    assert subsystems["database"]["status"] == "healthy"
    assert report["hardware"]["status"] == "healthy"
    assert report["overall_status"] in {"degraded", "critical"}


def test_health_service_remote_access_missing_status(tmp_path: Path):
    hardware_path = tmp_path / "hardware.yaml"
    system_path = tmp_path / "default.json"
    db_path = tmp_path / "lawnberry.db"

    _write_hardware_config(hardware_path)
    _write_system_config(system_path, remote_access=True)
    _initialize_database(db_path)

    service = HealthService(
        hardware_config_path=hardware_path,
        system_config_path=system_path,
        remote_access_status_path=tmp_path / "remote_access_status.json",
        database_path=db_path,
        error_window_seconds=120,
        sensor_health_provider=_fake_sensor_health,
        dependency_provider=_fake_dependencies,
    )

    report = service.evaluate()
    remote_status = report["subsystems"]["remote_access"]

    assert remote_status["status"] == "degraded"
    assert report["overall_status"] in {"degraded", "critical"}


def test_health_service_includes_error_alerts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hardware_path = tmp_path / "hardware.yaml"
    system_path = tmp_path / "default.json"
    db_path = tmp_path / "lawnberry.db"

    _write_hardware_config(hardware_path)
    _write_system_config(system_path, remote_access=False)
    _initialize_database(db_path)

    monkeypatch.setattr(
        observability.config,
        "error_rate_alert_threshold",
        1.0,
        raising=False,
    )

    service = HealthService(
        hardware_config_path=hardware_path,
        system_config_path=system_path,
        remote_access_status_path=tmp_path / "remote_access_status.json",
        database_path=db_path,
        error_window_seconds=120,
        sensor_health_provider=_fake_sensor_health,
        dependency_provider=_fake_dependencies,
    )

    for _ in range(4):
        observability.record_error(origin="telemetry", message="stream failure")

    report = service.evaluate()

    assert any(alert.get("origin") == "telemetry" for alert in report.get("alerts", []))
    assert report["error_rates"].get("telemetry", {}).get("errors_last_window", 0) >= 4
