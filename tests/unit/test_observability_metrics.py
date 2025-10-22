import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.src.core.observability import MetricsCollector, observability


def test_collect_system_metrics_handles_missing_f_available(monkeypatch):
    collector = MetricsCollector()

    fake_stat = SimpleNamespace(
        f_blocks=100,
        f_frsize=4096,
        f_bavail=20,
        f_bfree=25,
    )

    def fake_statvfs(path: str):
        assert path == "/home/pi/lawnberry"
        return fake_stat

    real_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        path_str = str(self)
        if path_str == "/home/pi/lawnberry":
            return True
        if path_str == "/proc/meminfo":
            return False
        return real_exists(self)

    monkeypatch.setattr(os, "statvfs", fake_statvfs)
    monkeypatch.setattr(Path, "exists", fake_exists)

    metrics = collector.collect_system_metrics()

    expected_total = fake_stat.f_blocks * fake_stat.f_frsize
    expected_free = fake_stat.f_bavail * fake_stat.f_frsize
    expected_used = expected_total - expected_free
    expected_percent = (expected_used / expected_total) * 100

    assert metrics.disk_usage_percent == pytest.approx(expected_percent)


def test_observability_error_rate_alerts(monkeypatch):
    observability.reset_events_for_testing()
    original_threshold = observability.config.error_rate_alert_threshold
    original_cooldown = observability.config.error_rate_alert_cooldown_seconds

    try:
        observability.config.error_rate_alert_threshold = 1.0
        observability.config.error_rate_alert_cooldown_seconds = 0

        for _ in range(2):
            observability.record_error(origin="http_request", message="api error")

        result = observability.update_error_metrics_for_testing(window_seconds=60)
        assert result["counts"]["http_request"] == 2
        assert result["rates"]["http_request"] == pytest.approx(2.0)

        snapshot = observability.get_metrics_snapshot()
        gauges = snapshot.get("gauges", {})
        assert gauges["error_rate_per_minute_http_request"] == pytest.approx(2.0)

        alerts = observability.get_recent_events(event_type="alert", within_seconds=60)
        assert len(alerts) == 1
        assert alerts[0]["origin"] == "http_request"
    finally:
        observability.config.error_rate_alert_threshold = original_threshold
        observability.config.error_rate_alert_cooldown_seconds = original_cooldown
        observability.reset_events_for_testing()
