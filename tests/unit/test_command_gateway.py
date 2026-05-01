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


# ---- Phase B: drive outcomes ----

@pytest.mark.asyncio
async def test_dispatch_drive_blocked_when_emergency_active():
    from backend.src.control.commands import CommandStatus, DriveCommand, EmergencyTrigger

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.5, right=0.5, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.BLOCKED
    assert "emergency" in (outcome.status_reason or "").lower() or outcome.status_reason is not None


@pytest.mark.asyncio
async def test_dispatch_drive_queued_when_no_hardware():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()  # robohat.status.serial_connected = False
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.QUEUED


@pytest.mark.asyncio
async def test_dispatch_drive_legacy_queued_when_no_hardware():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.95, right=0.55, source="legacy", duration_ms=0, legacy=True)
    )
    assert outcome.status in (CommandStatus.QUEUED, CommandStatus.ACCEPTED)


# ---- Phase B: blade outcomes ----

@pytest.mark.asyncio
async def test_dispatch_blade_blocked_while_emergency_active():
    from backend.src.control.commands import (
        BladeCommand, CommandStatus, EmergencyTrigger,
    )

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.dispatch_blade(
        BladeCommand(active=True, source="manual")
    )
    assert outcome.status == CommandStatus.BLOCKED


@pytest.mark.asyncio
async def test_dispatch_blade_blocked_while_motors_active():
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    outcome = await gw.dispatch_blade(
        BladeCommand(active=True, source="manual", motors_active=True)
    )
    assert outcome.status == CommandStatus.BLOCKED
    assert "motors_active" in (outcome.status_reason or "")


@pytest.mark.asyncio
async def test_dispatch_blade_disable_always_accepted():
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    outcome = await gw.dispatch_blade(
        BladeCommand(active=False, source="manual", motors_active=True)
    )
    assert outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED)


# ---- Phase D: reset_for_testing ----

@pytest.mark.asyncio
async def test_reset_for_testing_clears_all_state():
    from backend.src.control.commands import EmergencyTrigger

    gw, safety, blade = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    assert gw.is_emergency_active() is True
    gw.reset_for_testing()
    assert gw.is_emergency_active() is False
    assert safety["emergency_stop_active"] is False
    assert blade["active"] is False


# ---- Phase E: firmware preflight ----

@pytest.mark.asyncio
async def test_dispatch_drive_blocked_firmware_unknown():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    # Simulate robohat connected but firmware_version is None
    gw._robohat = MagicMock(
        status=MagicMock(serial_connected=True, firmware_version=None)
    )
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.FIRMWARE_UNKNOWN


@pytest.mark.asyncio
async def test_dispatch_drive_blocked_firmware_incompatible():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    gw._robohat = MagicMock(
        status=MagicMock(serial_connected=True, firmware_version="0.0.1")
    )
    # 0.0.1 is not in SUPPORTED_FIRMWARE_VERSIONS
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.FIRMWARE_INCOMPATIBLE
