import asyncio
import pytest


@pytest.mark.asyncio
async def test_message_bus_pub_sub_latency_under_10ms():
    """Contract: Publish event, subscriber receives within <10ms (FR-008)."""
    try:
        from backend.src.core.message_bus import MessageBus  # noqa: F401
    except Exception:
        pytest.skip("MessageBus not implemented yet")

    bus = MessageBus()
    received = asyncio.get_event_loop().create_future()

    async def handler(msg):
        if not received.done():
            received.set_result(msg)

    await bus.subscribe("contract.test", handler)
    start = asyncio.get_event_loop().time()
    await bus.publish("contract.test", {"hello": "world"})
    msg = await asyncio.wait_for(received, timeout=0.1)
    end = asyncio.get_event_loop().time()

    assert msg["payload"]["hello"] == "world"
    assert (end - start) * 1000.0 < 10.0, "Message bus latency exceeded 10ms"
