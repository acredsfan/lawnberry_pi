import os
import os.path
from unittest.mock import MagicMock

import pytest

# Skip placeholder integration tests by default to keep CI green.
# Run them explicitly by setting RUN_PLACEHOLDER_INTEGRATION=1
RUN_PLACEHOLDER = os.getenv("RUN_PLACEHOLDER_INTEGRATION", "0") == "1"

PLACEHOLDER_BASENAMES = {
    "test_autonomous_operation.py",
    "test_edge_cases.py",
    "test_hardware_compliance.py",
    "test_migration_v1_to_v2.py",
    "test_webui_experience.py",
    # Placeholders still pending implementation
    # Existing integration placeholders not yet implemented
    "test_acme_tls.py",
    "test_gps_loss_policy.py",
    "test_map_cost_control.py",
}


def pytest_collection_modifyitems(config, items):
    if RUN_PLACEHOLDER:
        return

    skip_placeholder = pytest.mark.skip(
        reason=(
            "Placeholder integration test skipped by default. "
            "Set RUN_PLACEHOLDER_INTEGRATION=1 to run."
        )
    )

    for item in items:
        basename = os.path.basename(str(item.fspath))
        if basename in PLACEHOLDER_BASENAMES:
            item.add_marker(skip_placeholder)


@pytest.fixture(autouse=True)
def reset_legacy_motor_state():
    """Reset _legacy_motors_active between integration tests to prevent state bleed."""
    import backend.src.api.rest as rest_module
    rest_module._legacy_motors_active = False
    yield
    rest_module._legacy_motors_active = False


@pytest.fixture(autouse=True)
def _ensure_runtime_for_integration_tests():
    """Inject a minimal RuntimeContext so tests that call gateway-wired endpoints work.

    Integration tests that use ASGITransport without lifespan need app.state.runtime
    populated. Tests that already set dependency_overrides (e.g. test_control_manual_flow)
    are unaffected — we only inject if get_runtime is not already overridden.
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
        sensor_manager=MagicMock(name="sensor_manager"),
        navigation=MagicMock(name="navigation"),
        mission_service=MagicMock(name="mission_service"),
        safety_state=_g._safety_state,
        blade_state=_g._blade_state,
        robohat=MagicMock(name="robohat"),
        websocket_hub=MagicMock(name="websocket_hub"),
        persistence=MagicMock(name="persistence"),
        command_gateway=_gw,
    )
    if get_runtime not in app.dependency_overrides:
        app.dependency_overrides[get_runtime] = lambda: _runtime
        try:
            yield
        finally:
            app.dependency_overrides.pop(get_runtime, None)
    else:
        yield
