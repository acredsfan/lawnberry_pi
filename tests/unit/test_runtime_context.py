"""Unit tests for RuntimeContext and get_runtime."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime


def _make_runtime(**overrides: Any) -> RuntimeContext:
    """Build a RuntimeContext where every field is a sentinel MagicMock unless overridden."""
    defaults: dict[str, Any] = {
        "config_loader": MagicMock(name="config_loader"),
        "hardware_config": MagicMock(name="hardware_config"),
        "safety_limits": MagicMock(name="safety_limits"),
        "sensor_manager": MagicMock(name="sensor_manager"),
        "navigation": MagicMock(name="navigation"),
        "mission_service": MagicMock(name="mission_service"),
        "safety_state": {"emergency_stop_active": False, "estop_reason": None},
        "blade_state": {"active": False},
        "robohat": MagicMock(name="robohat"),
        "websocket_hub": MagicMock(name="websocket_hub"),
        "persistence": MagicMock(name="persistence"),
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)


def test_runtime_context_holds_all_required_fields():
    runtime = _make_runtime()
    for field_name in (
        "config_loader",
        "hardware_config",
        "safety_limits",
        "sensor_manager",
        "navigation",
        "mission_service",
        "safety_state",
        "blade_state",
        "robohat",
        "websocket_hub",
        "persistence",
    ):
        assert hasattr(runtime, field_name), f"missing field: {field_name}"


def test_runtime_context_safety_state_is_a_live_reference():
    """Mutations to runtime.safety_state must propagate (it's the same dict, not a copy)."""
    shared = {"emergency_stop_active": False}
    runtime = _make_runtime(safety_state=shared)
    runtime.safety_state["emergency_stop_active"] = True
    assert shared["emergency_stop_active"] is True


def test_get_runtime_returns_app_state_runtime():
    app = FastAPI()
    app.state.runtime = _make_runtime()

    @app.get("/probe")
    def probe(runtime: RuntimeContext = pytest.importorskip("fastapi").Depends(get_runtime)):
        return {"has_navigation": runtime.navigation is not None}

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 200
        assert response.json() == {"has_navigation": True}


def test_get_runtime_raises_runtime_error_when_not_initialized():
    app = FastAPI()
    # Deliberately do NOT set app.state.runtime.

    @app.get("/probe")
    def probe(runtime: RuntimeContext = pytest.importorskip("fastapi").Depends(get_runtime)):
        return {"ok": True}

    # raise_server_exceptions=False required: Starlette >=0.21 TestClient
    # re-raises unhandled server exceptions by default; we want the HTTP 500.
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/probe")
        # FastAPI surfaces dependency errors as 500.
        assert response.status_code == 500


def test_dependency_override_replaces_get_runtime():
    """Tests inject fake runtimes via app.dependency_overrides — the canonical pattern."""
    app = FastAPI()
    app.state.runtime = _make_runtime()

    @app.get("/probe")
    def probe(runtime: RuntimeContext = pytest.importorskip("fastapi").Depends(get_runtime)):
        return {"nav_kind": type(runtime.navigation).__name__}

    fake_runtime = _make_runtime(navigation="not-a-mock")
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        with TestClient(app) as client:
            response = client.get("/probe")
            assert response.status_code == 200
            assert response.json() == {"nav_kind": "str"}
    finally:
        app.dependency_overrides.clear()
