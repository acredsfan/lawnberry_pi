import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from backend.src.services.websocket_hub import WebSocketHub


def test_bind_app_state_syncs_hardware_config_and_sets_hub_reference():
    hub = WebSocketHub()
    state = SimpleNamespace(hardware_config="hw-config", sensor_manager=None, ntrip_forwarder=None)

    hub.bind_app_state(state)

    assert hub._app_state.hardware_config == "hw-config"
    assert state.websocket_hub is hub


@pytest.mark.asyncio
async def test_ensure_sensor_manager_reuses_app_state_and_syncs_forwarder():
    hub = WebSocketHub()
    manager = MagicMock()
    forwarder = MagicMock()
    hub._app_state.sensor_manager = manager
    hub._app_state.ntrip_forwarder = forwarder

    with patch('backend.src.services.websocket_hub.telemetry_service.initialize_sensors', new=AsyncMock()) as init_sensors:
        result = await hub._ensure_sensor_manager()

    init_sensors.assert_not_awaited()
    assert result is manager
    assert hub._sensor_manager is manager
    assert hub._ntrip_forwarder is forwarder