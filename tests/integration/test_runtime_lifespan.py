"""Integration test: lifespan startup populates app.state.runtime."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext


def test_lifespan_startup_assigns_runtime_to_app_state():
    """After app startup runs, app.state.runtime is a populated RuntimeContext.

    Field-by-field expectations:

    - config_loader, hardware_config, safety_limits: always present (loaded from YAML).
    - navigation, mission_service, websocket_hub, persistence: always present.
    - safety_state, blade_state: live references to the same dict objects in
      core.globals — verified by `is` identity.
    - robohat: may be None in SIM_MODE if hardware probe didn't yield a service.
      We only assert it's a known-state value (None or an instance).
    - sensor_manager: exposed as a @property on RuntimeContext that reads
      AppState.sensor_manager live (Issue #44). After lifespan startup, the
      telemetry loop lazy-initializes AppState.sensor_manager, so the live
      read may yield either None or a SensorManager instance — but it must
      reflect AppState's current value by identity, not a snapshot.
    """
    from backend.src.main import app

    with TestClient(app) as _client:
        runtime = getattr(app.state, "runtime", None)
        assert runtime is not None, "lifespan did not assign app.state.runtime"
        assert isinstance(runtime, RuntimeContext)

        # Always-populated fields.
        for field_name in (
            "config_loader",
            "hardware_config",
            "safety_limits",
            "navigation",
            "mission_service",
            "websocket_hub",
            "persistence",
        ):
            assert getattr(runtime, field_name) is not None, (
                f"runtime.{field_name} should not be None after lifespan startup"
            )

        # Live-reference identity for the dict globals.
        from backend.src.core import globals as global_state

        assert runtime.safety_state is global_state._safety_state
        assert runtime.blade_state is global_state._blade_state

        # robohat may legitimately be None in SIM_MODE; only assert the slot
        # exists (which dataclass guarantees structurally).
        assert hasattr(runtime, "robohat")

        # sensor_manager is now a live property delegating to AppState
        # (Issue #44). Identity must hold regardless of whether telemetry
        # has lazy-initialized it yet.
        from backend.src.core.state_manager import AppState

        assert runtime.sensor_manager is AppState.get_instance().sensor_manager
