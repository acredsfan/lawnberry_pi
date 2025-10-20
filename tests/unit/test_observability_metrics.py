import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.src.core.observability import MetricsCollector


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
