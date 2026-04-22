"""Tests for websocket_hub broadcast_to_topic fan-out with timeout."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.src.services.websocket_hub import WebSocketHub


@pytest.mark.asyncio
async def test_broadcast_slow_client_times_out():
    """A slow client must not block the rest of the fan-out."""
    hub = WebSocketHub.__new__(WebSocketHub)
    hub.clients = {}
    hub.subscriptions = {"telemetry.nav": set()}
    hub.calibration_data = {}
    hub._calibration_lock = asyncio.Lock()

    async def _fast_send(msg):
        pass  # returns immediately

    async def _slow_send(msg):
        await asyncio.sleep(10)  # simulates a stalled client

    fast = MagicMock()
    fast.send_text = AsyncMock(side_effect=_fast_send)
    slow = MagicMock()
    slow.send_text = AsyncMock(side_effect=_slow_send)

    hub.clients["fast"] = fast
    hub.clients["slow"] = slow
    hub.subscriptions["telemetry.nav"].add("fast")
    hub.subscriptions["telemetry.nav"].add("slow")

    # Must complete well within the 2 s timeout + margin
    await asyncio.wait_for(
        hub.broadcast_to_topic("telemetry.nav", {"heading": 90}),
        timeout=4.0,
    )

    # Fast client received message; slow one was dropped
    fast.send_text.assert_called_once()
    assert "slow" not in hub.clients
