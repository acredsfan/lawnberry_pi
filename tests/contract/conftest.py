import os
import os.path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Skip placeholder WebSocket topic tests by default until implemented
RUN_PLACEHOLDER = os.getenv("RUN_PLACEHOLDER_CONTRACT", "0") == "1"

# Placeholder-gated contract tests for upcoming phases
# These are authored first (TDD) and skipped by default to keep CI green.
# Enable with RUN_PLACEHOLDER_CONTRACT=1 to execute (expected to fail until implemented).
PLACEHOLDER_BASENAMES = {
    # Phase 3: Sensors & Extended Safety contract tests
    "test_tof_sensors.py",
    "test_imu_tilt.py",
    "test_bme280.py",
    "test_ina3221.py",
    "test_sensor_fusion.py",
    # Phase 4: Navigation contract tests
    "test_gps.py",
    "test_geofence.py",
    "test_waypoint_navigation.py",
    "test_navigation_modes.py",
}


@pytest.fixture(autouse=True)
def _ensure_runtime_for_contract_tests():
    """Inject a minimal RuntimeContext so contract tests can call gateway-wired endpoints.

    Contract tests use ASGITransport without running lifespan, so app.state.runtime
    is never built. This fixture provides a minimal runtime that covers emergency endpoint
    needs (command_gateway). Tests that need specific state should use dependency_overrides.
    """
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as _g
    from backend.src.core.runtime import RuntimeContext, get_runtime
    from backend.src.main import app

    _gw = MotorCommandGateway(
        safety_state=_g._safety_state,
        blade_state=_g._blade_state,
        client_emergency=_g._client_emergency,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
    )
    _runtime = RuntimeContext(
        config_loader=MagicMock(name="config_loader"),
        hardware_config=MagicMock(name="hardware_config"),
        safety_limits=MagicMock(name="safety_limits"),
        navigation=MagicMock(name="navigation"),
        mission_service=MagicMock(name="mission_service"),
        safety_state=_g._safety_state,
        blade_state=_g._blade_state,
        robohat=MagicMock(name="robohat"),
        websocket_hub=MagicMock(name="websocket_hub"),
        persistence=MagicMock(name="persistence"),
        command_gateway=_gw,
    )
    # Only inject if the test hasn't already overridden get_runtime
    if get_runtime not in app.dependency_overrides:
        app.dependency_overrides[get_runtime] = lambda: _runtime
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_runtime, None)
    else:
        yield


def pytest_collection_modifyitems(config, items):
    if RUN_PLACEHOLDER:
        return

    skip_placeholder = pytest.mark.skip(
        reason=(
            "Placeholder contract test skipped by default. "
            "Set RUN_PLACEHOLDER_CONTRACT=1 to run."
        )
    )

    for item in items:
        basename = os.path.basename(str(item.fspath))
        if basename in PLACEHOLDER_BASENAMES:
            item.add_marker(skip_placeholder)
