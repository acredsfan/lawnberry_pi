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


# ── get_cached_telemetry tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_cached_telemetry_returns_snapshot_when_available():
    """get_cached_telemetry() must return existing snapshot immediately."""
    hub = WebSocketHub.__new__(WebSocketHub)
    hub._last_telemetry_snapshot = {"heading": 45.0, "source": "hardware"}
    hub._last_telemetry_at = asyncio.get_event_loop().time()

    result = await hub.get_cached_telemetry()

    assert result["heading"] == 45.0
    assert result["source"] == "hardware"


@pytest.mark.asyncio
async def test_get_cached_telemetry_returns_unavailable_when_no_cache():
    """get_cached_telemetry() must return fail-safe sentinel before first telemetry cycle."""
    hub = WebSocketHub.__new__(WebSocketHub)
    hub._last_telemetry_snapshot = None
    hub._last_telemetry_at = 0.0

    result = await hub.get_cached_telemetry()

    assert result == {"source": "unavailable"}


@pytest.mark.asyncio
async def test_get_cached_telemetry_returns_stale_snapshot_without_blocking():
    """get_cached_telemetry() must return stale data rather than triggering a live read.

    The safety gate in the drive endpoint handles staleness independently.
    """
    hub = WebSocketHub.__new__(WebSocketHub)
    hub._last_telemetry_snapshot = {"heading": 180.0, "source": "hardware"}
    # Simulate a very old snapshot (100 seconds ago).
    hub._last_telemetry_at = asyncio.get_event_loop().time() - 100.0

    # Must return stale cache — NOT call _generate_telemetry().
    result = await hub.get_cached_telemetry()

    assert result["heading"] == 180.0
    # Returned copy must not be the same dict object (shallow copy contract).
    assert result is not hub._last_telemetry_snapshot


@pytest.mark.asyncio
async def test_get_cached_telemetry_returns_shallow_copy():
    """Mutation of the returned dict must not corrupt the shared snapshot."""
    hub = WebSocketHub.__new__(WebSocketHub)
    hub._last_telemetry_snapshot = {"heading": 90.0}
    hub._last_telemetry_at = asyncio.get_event_loop().time()

    result = await hub.get_cached_telemetry()
    result["heading"] = 999.0

    assert hub._last_telemetry_snapshot["heading"] == 90.0


# ── telemetry.power always-broadcast tests ───────────────────────────────────


def _make_hub_with_subscriber(topic: str) -> tuple:
    """Return (hub, client_ws_mock) with one subscriber on *topic*."""
    hub = WebSocketHub.__new__(WebSocketHub)
    hub.clients = {}
    hub.subscriptions = {topic: set()}
    hub.calibration_data = {}
    hub._calibration_lock = asyncio.Lock()

    ws = MagicMock()
    ws.send_text = AsyncMock()
    hub.clients["c1"] = ws
    hub.subscriptions[topic].add("c1")
    return hub, ws


@pytest.mark.asyncio
async def test_power_topic_broadcast_when_power_key_present():
    """telemetry.power is broadcast when the dict contains a 'power' key (normal case)."""
    hub, ws = _make_hub_with_subscriber("telemetry.power")

    telemetry = {
        "power": {"battery_voltage": 12.5, "battery_current": 1.0},
        "power_status": "ok",
        "battery": {"percentage": 80.0, "voltage": 12.5},
        "source": "hardware",
        "position": {},
        "imu": {},
    }
    await hub._broadcast_telemetry_topics(telemetry)

    ws.send_text.assert_called_once()
    import json
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["topic"] == "telemetry.power"
    assert payload["data"]["power"]["battery_voltage"] == 12.5


@pytest.mark.asyncio
async def test_power_topic_broadcast_when_power_is_null_payload():
    """telemetry.power is still broadcast when the power block holds all-null fields."""
    hub, ws = _make_hub_with_subscriber("telemetry.power")

    # This is what _format_telemetry now emits when sensor data is unavailable
    telemetry = {
        "power": {
            "battery_voltage": None,
            "battery_current": None,
            "battery_power": None,
            "solar_voltage": None,
            "solar_current": None,
            "solar_power": None,
            "solar_yield_today_wh": None,
            "battery_consumed_today_wh": None,
            "load_current": None,
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
        "power_status": "unavailable",
        "battery": {"percentage": 0.0, "voltage": 0.0},
        "source": "hardware",
        "position": {},
        "imu": {},
    }
    await hub._broadcast_telemetry_topics(telemetry)

    ws.send_text.assert_called_once()
    import json
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["topic"] == "telemetry.power"
    # power_status forwarded in the message
    assert payload["data"]["power"]["battery_voltage"] is None
