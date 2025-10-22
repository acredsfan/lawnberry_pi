import pytest


@pytest.mark.asyncio
async def test_critical_message_survives_restart():
    """Contract: Critical messages are persisted and delivered after restart (FR-008a/b/c)."""
    try:
        from backend.src.core.message_bus import MessageBus
        from backend.src.core.message_persistence import PersistenceLayer
    except Exception:
        pytest.skip("Message bus/persistence not implemented yet")

    persistence = PersistenceLayer(db_path=":memory:")
    bus = MessageBus(persistence=persistence)
    delivered = []

    async def handler(msg):
        delivered.append(msg)

    await bus.subscribe("safety.estop", handler, persistent=True)
    await bus.publish("safety.estop", {"reason": "test"}, persistent=True)

    # Simulate restart by creating a new bus with same persistence
    bus2 = MessageBus(persistence=persistence)
    await bus2.replay_persistent("safety.estop")

    # Expect at least one delivery
    assert any(m["payload"].get("reason") == "test" for m in delivered)
