"""Verify main.py attaches a TelemetryCapture when LAWNBERRY_CAPTURE_PATH is set."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_nav_singleton():
    """Force a fresh NavigationService for each wiring test."""
    from backend.src.services import navigation_service as ns_module

    ns_module.NavigationService._instance = None
    yield
    ns_module.NavigationService._instance = None


def test_capture_attached_when_env_var_set(tmp_path: Path, monkeypatch):
    target = tmp_path / "run.jsonl"
    monkeypatch.setenv("LAWNBERRY_CAPTURE_PATH", str(target))

    from backend.src.main import _maybe_attach_telemetry_capture
    from backend.src.services.navigation_service import NavigationService

    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    assert nav._capture is not None
    assert nav._capture.path == target


def test_capture_not_attached_when_env_var_absent(monkeypatch):
    monkeypatch.delenv("LAWNBERRY_CAPTURE_PATH", raising=False)

    from backend.src.main import _maybe_attach_telemetry_capture
    from backend.src.services.navigation_service import NavigationService

    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    assert nav._capture is None


def test_capture_not_attached_when_env_var_empty(monkeypatch):
    monkeypatch.setenv("LAWNBERRY_CAPTURE_PATH", "")

    from backend.src.main import _maybe_attach_telemetry_capture
    from backend.src.services.navigation_service import NavigationService

    nav = NavigationService.get_instance()
    _maybe_attach_telemetry_capture(nav)
    assert nav._capture is None
