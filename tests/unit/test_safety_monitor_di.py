"""Tests for ARCH-006: SafetyMonitor must not import from api.rest (circular dep)."""
import importlib.util
import sys
import pytest


def test_safety_monitor_has_no_circular_import():
    """safety_monitor.py must not contain 'from ..api.rest import' at source level."""
    spec = importlib.util.find_spec("backend.src.safety.safety_monitor")
    assert spec is not None
    with open(spec.origin) as f:
        content = f.read()
    assert "from ..api.rest import" not in content, \
        "safety_monitor.py must not import from api.rest (circular dependency)"


@pytest.mark.asyncio
async def test_safety_monitor_broadcasts_when_hub_injected():
    """SafetyMonitor broadcasts to injected hub."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.src.safety.safety_monitor import SafetyMonitor
    from backend.src.models.safety_interlock import SafetyInterlock, InterlockState, InterlockType

    hub = MagicMock()
    hub.broadcast_to_topic = AsyncMock()

    monitor = SafetyMonitor(websocket_hub=hub)
    interlock = SafetyInterlock(
        interlock_id="test-001",
        interlock_type=InterlockType.TILT_DETECTED,
        triggered_at_us=0,
        state=InterlockState.ACTIVE,
    )
    await monitor.handle_interlock_event("activate", interlock)

    hub.broadcast_to_topic.assert_called_once()
    topic = hub.broadcast_to_topic.call_args[0][0]
    assert topic == "system.safety"


@pytest.mark.asyncio
async def test_safety_monitor_no_broadcast_without_hub():
    """SafetyMonitor must not raise when no hub injected."""
    from backend.src.safety.safety_monitor import SafetyMonitor
    from backend.src.models.safety_interlock import SafetyInterlock, InterlockState, InterlockType

    monitor = SafetyMonitor()  # no hub
    interlock = SafetyInterlock(
        interlock_id="test-002",
        interlock_type=InterlockType.TILT_DETECTED,
        triggered_at_us=0,
        state=InterlockState.ACTIVE,
    )
    await monitor.handle_interlock_event("activate", interlock)  # must not raise


@pytest.mark.asyncio
async def test_safety_monitor_set_hub_after_construction():
    """set_websocket_hub() wires hub post-construction (for main.py lifespan pattern)."""
    from unittest.mock import AsyncMock, MagicMock
    from backend.src.safety.safety_monitor import SafetyMonitor
    from backend.src.models.safety_interlock import SafetyInterlock, InterlockState, InterlockType

    hub = MagicMock()
    hub.broadcast_to_topic = AsyncMock()

    monitor = SafetyMonitor()
    monitor.set_websocket_hub(hub)

    interlock = SafetyInterlock(
        interlock_id="test-003",
        interlock_type=InterlockType.EMERGENCY_STOP,
        triggered_at_us=0,
        state=InterlockState.ACTIVE,
    )
    await monitor.handle_interlock_event("activate", interlock)
    hub.broadcast_to_topic.assert_called_once()
