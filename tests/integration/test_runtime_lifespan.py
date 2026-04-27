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
    - sensor_manager: KNOWN GAP — captured here as a snapshot of
      AppState.sensor_manager at construction time, but AppState lazily
      initializes sensor_manager via the telemetry loop AFTER lifespan startup
      yields. So this is typically None at runtime construction and stays None
      even after AppState's attribute is later set. Tasks 4 and 5 of §1 do not
      consume runtime.sensor_manager, so this gap is acceptable for now. A
      future task should convert sensor_manager to a property that delegates
      to AppState for live reads (see comment in main.py near construction).
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

        # sensor_manager: known snapshot gap — see docstring above. Don't
        # assert it's non-None here, because that would lock in the bug or
        # produce a flaky test depending on how lazy init landed in this run.
        assert hasattr(runtime, "sensor_manager")
