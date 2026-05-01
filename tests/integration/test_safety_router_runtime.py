"""Integration test: safety router endpoints work via injected RuntimeContext."""
from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime


def _make_runtime(**overrides: Any) -> RuntimeContext:
    defaults: dict[str, Any] = {
        "config_loader": MagicMock(name="config_loader"),
        "hardware_config": MagicMock(name="hardware_config"),
        "safety_limits": MagicMock(name="safety_limits"),
        "navigation": MagicMock(name="navigation"),
        "mission_service": MagicMock(name="mission_service"),
        "safety_state": {"emergency_stop_active": True, "estop_reason": "test"},
        "blade_state": {"active": True},
        "robohat": MagicMock(name="robohat"),
        "websocket_hub": MagicMock(name="websocket_hub"),
        "persistence": MagicMock(name="persistence"),
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)


def test_clear_emergency_stop_resets_safety_state_via_runtime():
    """Calling the clear-emergency-stop endpoint mutates runtime.safety_state.

    The actual endpoint path is /api/v2/control/emergency_clear (safety router
    has no prefix of its own; it is mounted at /api/v2 in main.py).
    """
    from backend.src.main import app

    fake_runtime = _make_runtime()
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        with TestClient(app) as client:
            # Sanity: starts with emergency latched on the fake runtime.
            assert fake_runtime.safety_state["emergency_stop_active"] is True
            response = client.post(
                "/api/v2/control/emergency_clear",
                json={"confirmation": True, "reason": "integration test"},
            )
            assert response.status_code in (200, 204), (
                f"unexpected status: {response.status_code} body={response.text}"
            )
            assert fake_runtime.safety_state["emergency_stop_active"] is False
            assert fake_runtime.blade_state["active"] is False
    finally:
        app.dependency_overrides.clear()


def test_safety_endpoints_do_not_import_globals_from_rest():
    """Regression guard: safety.py must not depend on rest.py for _safety_state/_blade_state.

    _client_emergency import is still allowed (deferred to §4 motor command gateway).
    """
    from backend.src.api import safety

    src = safety.__file__
    text = open(src).read()
    assert "from .rest import _safety_state" not in text, (
        "safety.py still imports _safety_state from rest.py"
    )
    assert "from .rest import _blade_state" not in text, (
        "safety.py still imports _blade_state from rest.py"
    )
    # Combined-import form (e.g., `from .rest import _blade_state, _safety_state`)
    # should also be rejected — match any line that imports those names from rest.
    pattern = re.compile(r"from \.rest import [^\n]*(_safety_state|_blade_state)")
    assert not pattern.search(text), (
        "safety.py still imports _safety_state or _blade_state from rest.py "
        "in some import form"
    )
