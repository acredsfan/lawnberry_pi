from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.src.api.health import (
    health_api_v2,
    health_liveness,
    health_readiness,
    health_root,
    health_service,
)


def test_health_endpoints_surface_service_evaluation(monkeypatch):
    sample_report: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "overall_status": "healthy",
        "hardware": {"status": "healthy"},
        "sensor_health": {"status": "healthy"},
        "subsystems": {"api": {"status": "healthy"}},
        "dependencies": {"metrics_collector": {"status": "healthy"}},
        "metrics": {},
        "alerts": [],
        "error_rates": {},
    }

    monkeypatch.setattr(health_service, "evaluate", lambda: sample_report)

    assert health_root() == sample_report
    assert health_api_v2() == sample_report

    readiness = health_readiness()
    assert readiness["status"] == sample_report["overall_status"]
    assert readiness["sensor_health"] == sample_report["sensor_health"]
    assert readiness["dependencies"] == sample_report["dependencies"]

    assert health_liveness()["status"] == "alive"
