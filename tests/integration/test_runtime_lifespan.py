"""Integration test: lifespan startup populates app.state.runtime."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext


def test_lifespan_startup_assigns_runtime_to_app_state():
    """After app startup runs, app.state.runtime is a populated RuntimeContext."""
    from backend.src.main import app

    with TestClient(app) as _client:
        runtime = getattr(app.state, "runtime", None)
        assert runtime is not None, "lifespan did not assign app.state.runtime"
        assert isinstance(runtime, RuntimeContext)
        # Sanity checks on key fields.
        assert runtime.navigation is not None
        assert runtime.mission_service is not None
        assert runtime.websocket_hub is not None
        assert runtime.persistence is not None
        # safety_state and blade_state must be the live globals dicts.
        from backend.src.core import globals as global_state

        assert runtime.safety_state is global_state._safety_state
        assert runtime.blade_state is global_state._blade_state
