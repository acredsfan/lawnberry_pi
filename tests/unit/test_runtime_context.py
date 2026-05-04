"""Unit tests for RuntimeContext and get_runtime."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime


def _make_runtime(**overrides: Any) -> RuntimeContext:
    """Build a RuntimeContext where every field is a sentinel MagicMock unless overridden."""
    defaults: dict[str, Any] = {
        "config_loader": MagicMock(name="config_loader"),
        "hardware_config": MagicMock(name="hardware_config"),
        "safety_limits": MagicMock(name="safety_limits"),
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
    from dataclasses import fields

    expected = {
        "config_loader",
        "hardware_config",
        "safety_limits",
        "navigation",
        "mission_service",
        "safety_state",
        "blade_state",
        "robohat",
        "websocket_hub",
        "persistence",
        "command_gateway",
        "localization",
        "map_repository",
        "mission_repository",
        "settings_repository",
        "calibration_repository",
        "telemetry_repository",
        "event_store",
        "persistence_mode",
    }
    actual = {f.name for f in fields(RuntimeContext)}
    assert actual == expected, f"field set drift: extra={actual-expected}, missing={expected-actual}"

    # Also check we can construct an instance with all fields populated.
    runtime = _make_runtime()
    for name in expected:
        assert hasattr(runtime, name)

    # sensor_manager is exposed as a @property (Issue #44), not a dataclass field.
    assert hasattr(runtime, "sensor_manager")


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
    def probe(runtime: RuntimeContext = Depends(get_runtime)):
        return {"has_navigation": runtime.navigation is not None}

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 200
        assert response.json() == {"has_navigation": True}


def test_get_runtime_raises_runtime_error_when_not_initialized():
    app = FastAPI()
    # Deliberately do NOT set app.state.runtime.

    @app.get("/probe")
    def probe(runtime: RuntimeContext = Depends(get_runtime)):
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
    def probe(runtime: RuntimeContext = Depends(get_runtime)):
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


def test_sensor_manager_is_a_property_not_a_dataclass_field():
    """Issue #44: sensor_manager must be a @property delegating to AppState,
    not a dataclass field captured as a snapshot at construction time."""
    from dataclasses import fields

    field_names = {f.name for f in fields(RuntimeContext)}
    assert "sensor_manager" not in field_names, (
        "sensor_manager is still a dataclass field; convert it to a @property"
    )
    assert isinstance(
        getattr(RuntimeContext, "sensor_manager", None), property
    ), "sensor_manager must be exposed as a @property on RuntimeContext"


def test_runtime_context_constructor_rejects_sensor_manager_kwarg():
    """Once converted to a property, the dataclass __init__ must not accept
    sensor_manager= — silent acceptance would mask call-site bugs."""
    with pytest.raises(TypeError):
        _make_runtime(sensor_manager=MagicMock())  # type: ignore[arg-type]


def test_runtime_sensor_manager_reads_live_from_appstate():
    """runtime.sensor_manager must reflect the current AppState value, not a
    snapshot taken at construction time. This is the entire point of #44."""
    from backend.src.core.state_manager import AppState

    app_state = AppState.get_instance()
    original = app_state.sensor_manager
    try:
        sentinel_a = object()
        app_state.sensor_manager = sentinel_a
        runtime = _make_runtime()
        assert runtime.sensor_manager is sentinel_a

        # Mutate AppState after runtime construction; live reads must follow.
        sentinel_b = object()
        app_state.sensor_manager = sentinel_b
        assert runtime.sensor_manager is sentinel_b
    finally:
        app_state.sensor_manager = original


# --- LocalizationService in RuntimeContext ---


def test_runtime_context_accepts_localization_field():
    """RuntimeContext must accept a localization field without error."""
    runtime = _make_runtime(localization=None)
    assert runtime.localization is None


def test_runtime_context_localization_can_be_set():
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    runtime = _make_runtime(localization=loc)
    assert isinstance(runtime.localization, LocalizationService)


def test_runtime_context_has_repository_slots() -> None:
    """RuntimeContext accepts all five repository fields (may be None)."""
    from backend.src.core.runtime import RuntimeContext

    ctx = RuntimeContext(
        config_loader=None,
        hardware_config=None,
        safety_limits=None,
        navigation=None,
        mission_service=None,
        safety_state={},
        blade_state={},
        robohat=None,
        websocket_hub=None,
        persistence=None,
        command_gateway=None,
        map_repository=None,
        mission_repository=None,
        settings_repository=None,
        calibration_repository=None,
        telemetry_repository=None,
    )
    assert ctx.map_repository is None
    assert ctx.mission_repository is None
    assert ctx.settings_repository is None
    assert ctx.calibration_repository is None
    assert ctx.telemetry_repository is None
