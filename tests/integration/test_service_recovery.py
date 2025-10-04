import os
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_message_bus_reconnect_and_replay():
    """Simulate subscriber crash and recovery with replay of persistent messages.

    This validates NFR-007: service recovery without data loss for critical topics.
    """
    os.environ["SIM_MODE"] = "1"

    from backend.src.core.message_bus import MessageBus
    from backend.src.core.message_persistence import PersistenceLayer

    persistence = PersistenceLayer(db_path=":memory:")
    bus = MessageBus(persistence=persistence)

    received: list[dict[str, Any]] = []

    async def handler(evt: dict[str, Any]) -> None:
        received.append(evt)

    # Subscribe and publish a persistent event
    await bus.subscribe("safety.estop", handler, persistent=True)
    await bus.publish("safety.estop", {"reason": "test"}, persistent=True)

    # Ensure immediate delivery for live handler
    assert any(r["payload"].get("reason") == "test" for r in received)

    # Simulate crash: drop handler references (new list for received)
    received_after: list[dict[str, Any]] = []

    async def handler_after(evt: dict[str, Any]) -> None:
        received_after.append(evt)

    # New subscriber after crash
    await bus.subscribe("safety.estop", handler_after, persistent=True)

    # Replay persistent messages and validate they are delivered to the new subscriber
    await bus.replay_persistent("safety.estop")

    assert any(r["payload"].get("reason") == "test" for r in received_after), (
        "Persistent messages should replay to new subscriber"
    )


@pytest.mark.asyncio
async def test_driver_registry_restart_on_failure(tmp_path):
    """Simulate driver crash and verify registry can restart it per config.

    Uses SIM_MODE=1 where drivers are mock objects, allowing identity checks.
    """
    os.environ["SIM_MODE"] = "1"

    from backend.src.core.driver_registry import DriverRegistry

    reg = DriverRegistry()
    drivers = reg.load()
    assert "gps" in drivers and reg.get("gps") is drivers["gps"]

    # Simulate failure of GPS driver and restart
    before = reg.get("gps")
    reg.mark_failed("gps")
    assert reg.get("gps") is None

    restarted = reg.restart("gps")
    assert restarted is not None
    assert reg.get("gps") is restarted
    # In SIM_MODE, restart should produce a different instance
    assert restarted is not before
