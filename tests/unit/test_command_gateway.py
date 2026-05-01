"""Unit tests for MotorCommandGateway — Phase A: emergency lifecycle."""
import pytest
from unittest.mock import MagicMock


def _make_gw():
    """Return (gateway, safety_state, blade_state) using a mocked rest module."""
    from backend.src.control.command_gateway import MotorCommandGateway

    safety = {"emergency_stop_active": False, "estop_reason": None}
    blade = {"active": False}
    client_em: dict = {}
    rest_mock = MagicMock()
    rest_mock._emergency_until = 0.0
    gw = MotorCommandGateway(
        safety_state=safety,
        blade_state=blade,
        client_emergency=client_em,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
        _rest_module=rest_mock,
    )
    return gw, safety, blade


def test_is_emergency_active_false_initially():
    gw, _, _ = _make_gw()
    assert gw.is_emergency_active() is False


@pytest.mark.asyncio
async def test_trigger_latches_safety_state():
    from backend.src.control.commands import CommandStatus, EmergencyTrigger

    gw, safety, blade = _make_gw()
    outcome = await gw.trigger_emergency(
        EmergencyTrigger(reason="test", source="operator")
    )
    assert outcome.status == CommandStatus.EMERGENCY_LATCHED
    assert safety["emergency_stop_active"] is True
    assert blade["active"] is False
    assert gw.is_emergency_active() is True


@pytest.mark.asyncio
async def test_trigger_is_idempotent():
    from backend.src.control.commands import CommandStatus, EmergencyTrigger

    gw, safety, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="first", source="operator"))
    outcome = await gw.trigger_emergency(EmergencyTrigger(reason="second", source="operator"))
    assert outcome.status == CommandStatus.EMERGENCY_LATCHED
    assert safety["emergency_stop_active"] is True


@pytest.mark.asyncio
async def test_clear_without_confirmation_returns_blocked():
    from backend.src.control.commands import CommandStatus, EmergencyClear, EmergencyTrigger

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.clear_emergency(EmergencyClear(confirmed=False))
    assert outcome.status == CommandStatus.BLOCKED
    assert gw.is_emergency_active() is True


@pytest.mark.asyncio
async def test_clear_with_confirmation_releases_latch():
    from backend.src.control.commands import CommandStatus, EmergencyClear, EmergencyTrigger

    gw, safety, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.clear_emergency(EmergencyClear(confirmed=True))
    assert outcome.status == CommandStatus.ACCEPTED
    assert outcome.idempotent is False
    assert safety["emergency_stop_active"] is False
    assert gw.is_emergency_active() is False


@pytest.mark.asyncio
async def test_clear_when_not_active_is_idempotent():
    from backend.src.control.commands import CommandStatus, EmergencyClear

    gw, _, _ = _make_gw()
    outcome = await gw.clear_emergency(EmergencyClear(confirmed=True))
    assert outcome.status == CommandStatus.ACCEPTED
    assert outcome.idempotent is True
