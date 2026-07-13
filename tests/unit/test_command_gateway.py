"""Unit tests for MotorCommandGateway — Phase A: emergency lifecycle."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class _FakeBladeController:
    async def initialize(self):
        return True

    async def set_active(self, active: bool, *, reason: str):
        from backend.src.services.blade_controller import BladeResult

        return BladeResult(
            ok=True,
            commanded_active=bool(active),
            acknowledged_active=bool(active),
        )

    async def emergency_stop(self, *, reason: str):
        from backend.src.services.blade_controller import BladeResult

        return BladeResult(ok=True, commanded_active=False, acknowledged_active=False)


class _FakeQualificationService:
    def __init__(self, reason_codes: list[str] | None = None):
        self.reason_codes = reason_codes or []

    def assert_current(self):
        if not self.reason_codes:
            return SimpleNamespace(record=SimpleNamespace(record_id="qualification-ok"))
        exc = RuntimeError("qualification blocked")
        exc.evaluation = SimpleNamespace(reason_codes=self.reason_codes)
        raise exc


def _make_gw():
    """Return (gateway, safety_state, blade_state) using a mocked rest module."""
    from unittest.mock import AsyncMock, MagicMock

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
    gw._check_manual_drive_interlocks = AsyncMock(return_value=[])
    gw.set_blade_controller(_FakeBladeController())
    gw.set_qualification_service(_FakeQualificationService())
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
async def test_dispatch_zero_drive_allowed_when_emergency_active():
    from backend.src.control.commands import CommandStatus, DriveCommand, EmergencyTrigger

    gw, _, _ = _make_gw()
    await gw.trigger_emergency(EmergencyTrigger(reason="x", source="operator"))
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.0, right=0.0, source="manual", duration_ms=200)
    )
    assert outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED)


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
        BladeCommand,
        CommandStatus,
        EmergencyTrigger,
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


@pytest.mark.asyncio
async def test_dispatch_blade_active_requires_qualification_service():
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    gw.set_qualification_service(None)

    outcome = await gw.dispatch_blade(BladeCommand(active=True, source="manual"))

    assert outcome.status == CommandStatus.BLOCKED
    assert outcome.status_reason == "QUALIFICATION_SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_dispatch_blade_active_blocks_failed_qualification():
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    gw.set_qualification_service(
        _FakeQualificationService(["QUALIFICATION_EVIDENCE_MISSING"])
    )

    outcome = await gw.dispatch_blade(BladeCommand(active=True, source="manual"))

    assert outcome.status == CommandStatus.BLOCKED
    assert "QUALIFICATION_EVIDENCE_MISSING" in (outcome.status_reason or "")


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
async def test_dispatch_drive_allowed_firmware_version_not_yet_received():
    # firmware_version=None means the version string hasn't arrived over UART yet
    # (firmware is responsive). Drive commands must be allowed through — blocking
    # here would prevent all motion immediately after backend startup.
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    gw._robohat = MagicMock(
        status=MagicMock(serial_connected=True, firmware_version=None)
    )
    gw._robohat.send_motor_command = AsyncMock(return_value=True)
    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status not in (CommandStatus.FIRMWARE_UNKNOWN, CommandStatus.FIRMWARE_INCOMPATIBLE)


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


@pytest.mark.asyncio
async def test_dispatch_blade_allowed_firmware_version_not_yet_received(monkeypatch):
    """firmware_version=None must not block blade commands — version arrives async at startup."""
    from unittest.mock import AsyncMock

    import backend.src.services.blade_service as bs_mod
    from backend.src.control.commands import BladeCommand, CommandStatus

    gw, _, _ = _make_gw()
    gw._robohat = MagicMock(
        status=MagicMock(serial_connected=True, firmware_version=None)
    )

    mock_blade_service = AsyncMock()
    mock_blade_service.initialize = AsyncMock(return_value=True)
    mock_blade_service.set_active = AsyncMock(return_value=True)
    monkeypatch.setattr(bs_mod, "get_blade_service", lambda: mock_blade_service)

    outcome = await gw.dispatch_blade(
        BladeCommand(active=True, source="manual")
    )
    assert outcome.status not in (CommandStatus.FIRMWARE_UNKNOWN, CommandStatus.FIRMWARE_INCOMPATIBLE)


@pytest.mark.asyncio
async def test_dispatch_drive_allowed_with_supported_firmware():
    """Gateway must not block dispatch when firmware version is in SUPPORTED_FIRMWARE_VERSIONS."""
    from unittest.mock import AsyncMock, MagicMock

    from backend.src.control.command_gateway import SUPPORTED_FIRMWARE_VERSIONS
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    good_version = next(iter(SUPPORTED_FIRMWARE_VERSIONS))
    mock_robohat = MagicMock()
    mock_robohat.status.serial_connected = True
    mock_robohat.status.firmware_version = good_version
    mock_robohat.send_motor_command = AsyncMock(return_value=True)
    gw._robohat = mock_robohat

    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status not in (
        CommandStatus.FIRMWARE_UNKNOWN,
        CommandStatus.FIRMWARE_INCOMPATIBLE,
    )


@pytest.mark.asyncio
async def test_mission_drive_lease_old_expiry_cannot_stop_newer_command():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    mock_robohat = MagicMock()
    mock_robohat.status.serial_connected = True
    mock_robohat.status.firmware_version = "10.0.0"
    mock_robohat.send_motor_command = AsyncMock(return_value=True)
    gw._robohat = mock_robohat
    gw._config_loader = MagicMock(
        get=MagicMock(return_value=(None, SimpleNamespace(autonomous_command_ttl_ms=80)))
    )

    first = await gw.dispatch_drive(
        DriveCommand(left=0.4, right=0.4, source="mission", duration_ms=0)
    )
    await asyncio.sleep(0.04)
    second = await gw.dispatch_drive(
        DriveCommand(left=0.5, right=0.5, source="mission", duration_ms=0)
    )
    await asyncio.sleep(0.06)

    assert first.status == CommandStatus.ACCEPTED
    assert second.status == CommandStatus.ACCEPTED
    assert mock_robohat.send_motor_command.await_count == 2

    await asyncio.sleep(0.04)
    assert mock_robohat.send_motor_command.await_args_list[-1].args == (0.0, 0.0)


@pytest.mark.asyncio
async def test_v18_zero_drive_cancels_existing_lease_without_new_delayed_stop():
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    mock_robohat = MagicMock()
    mock_robohat.status.serial_connected = True
    mock_robohat.status.firmware_version = "10.0.0"
    mock_robohat.send_motor_command = AsyncMock(return_value=True)
    gw._robohat = mock_robohat

    moving = await gw.dispatch_drive(
        DriveCommand(left=0.4, right=0.4, source="manual", duration_ms=100)
    )
    stopped = await gw.dispatch_drive(
        DriveCommand(left=0.0, right=0.0, source="manual", duration_ms=0)
    )
    await asyncio.sleep(0.6)

    assert moving.status == CommandStatus.ACCEPTED
    assert stopped.status == CommandStatus.ACCEPTED
    assert mock_robohat.send_motor_command.await_count == 2
    assert mock_robohat.send_motor_command.await_args_list[-1].args == (0.0, 0.0)


@pytest.mark.asyncio
async def test_v18_manual_drive_ignores_zero_tof_glitch(monkeypatch):
    from datetime import UTC, datetime

    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.control.commands import DriveCommand
    from backend.src.core.state_manager import AppState
    from backend.src.models.safety_limits import SafetyLimits
    from backend.src.services.navigation_service import NavigationService

    gw, _, _ = _make_gw()
    gw._check_manual_drive_interlocks = MotorCommandGateway._check_manual_drive_interlocks.__get__(
        gw, MotorCommandGateway
    )
    gw._config_loader = MagicMock(get=MagicMock(return_value=(None, SafetyLimits())))
    monkeypatch.setattr(
        NavigationService,
        "get_instance",
        lambda: SimpleNamespace(max_waypoint_accuracy_m=0.25),
    )
    AppState.get_instance().last_telemetry = {
        "source": "hardware",
        "timestamp": datetime.now(UTC).isoformat(),
        "position": {"latitude": 39.0, "longitude": -84.0, "accuracy": 0.03},
        "tof": {
            "left": {"distance_mm": 0},
            "right": {"distance_mm": 1200},
        },
    }

    interlocks = await gw._check_manual_drive_interlocks(
        DriveCommand(left=0.4, right=0.4, source="manual", duration_ms=200)
    )

    assert "obstacle_detected" not in interlocks


@pytest.mark.asyncio
async def test_v20_manual_drive_uses_operator_tof_cutoff_not_dynamic_floor(monkeypatch):
    from datetime import UTC, datetime

    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.control.commands import DriveCommand
    from backend.src.core.state_manager import AppState
    from backend.src.models.safety_limits import SafetyLimits
    from backend.src.services.navigation_service import NavigationService

    gw, _, _ = _make_gw()
    gw._check_manual_drive_interlocks = MotorCommandGateway._check_manual_drive_interlocks.__get__(
        gw, MotorCommandGateway
    )
    limits = SafetyLimits(
        tof_obstacle_distance_meters=0.0254,
        obstacle_min_clearance_m=0.55,
        obstacle_front_offset_m=0.25,
        obstacle_fixed_margin_m=0.2,
    )
    gw._config_loader = MagicMock(get=MagicMock(return_value=(None, limits)))
    monkeypatch.setattr(
        NavigationService,
        "get_instance",
        lambda: SimpleNamespace(max_waypoint_accuracy_m=0.25),
    )
    AppState.get_instance().last_telemetry = {
        "source": "hardware",
        "timestamp": datetime.now(UTC).isoformat(),
        "position": {"latitude": 39.0, "longitude": -84.0, "accuracy": 0.03},
        "tof": {
            "left": {"distance_mm": 500},
            "right": {"distance_mm": 600},
        },
    }

    interlocks = await gw._check_manual_drive_interlocks(
        DriveCommand(left=0.4, right=0.4, source="manual", duration_ms=200)
    )

    assert "obstacle_detected" not in interlocks


@pytest.mark.asyncio
async def test_v20_manual_drive_blocks_inside_operator_tof_cutoff(monkeypatch):
    from datetime import UTC, datetime

    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.control.commands import DriveCommand
    from backend.src.core.state_manager import AppState
    from backend.src.models.safety_limits import SafetyLimits
    from backend.src.services.navigation_service import NavigationService

    gw, _, _ = _make_gw()
    gw._check_manual_drive_interlocks = MotorCommandGateway._check_manual_drive_interlocks.__get__(
        gw, MotorCommandGateway
    )
    gw._config_loader = MagicMock(
        get=MagicMock(
            return_value=(None, SafetyLimits(tof_obstacle_distance_meters=0.0254))
        )
    )
    monkeypatch.setattr(
        NavigationService,
        "get_instance",
        lambda: SimpleNamespace(max_waypoint_accuracy_m=0.25),
    )
    AppState.get_instance().last_telemetry = {
        "source": "hardware",
        "timestamp": datetime.now(UTC).isoformat(),
        "position": {"latitude": 39.0, "longitude": -84.0, "accuracy": 0.03},
        "tof": {
            "left": {"distance_mm": 10},
            "right": {"distance_mm": 600},
        },
    }

    interlocks = await gw._check_manual_drive_interlocks(
        DriveCommand(left=0.4, right=0.4, source="manual", duration_ms=200)
    )

    assert "obstacle_detected" in interlocks


@pytest.mark.asyncio
async def test_v21_zero_drive_skips_manual_interlocks_with_stale_telemetry():
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.control.commands import DriveCommand
    from backend.src.core.state_manager import AppState

    gw, _, _ = _make_gw()
    gw._check_manual_drive_interlocks = MotorCommandGateway._check_manual_drive_interlocks.__get__(
        gw, MotorCommandGateway
    )
    AppState.get_instance().last_telemetry = {"source": "unavailable"}

    interlocks = await gw._check_manual_drive_interlocks(
        DriveCommand(left=0.0, right=0.0, source="manual", duration_ms=0)
    )

    assert interlocks == []


@pytest.mark.asyncio
async def test_dispatch_drive_ack_timeout_returns_ack_failed():
    """Simulated ack timeout: send_motor_command returns False -> ACK_FAILED outcome."""
    from unittest.mock import AsyncMock, MagicMock

    from backend.src.control.command_gateway import SUPPORTED_FIRMWARE_VERSIONS
    from backend.src.control.commands import CommandStatus, DriveCommand

    gw, _, _ = _make_gw()
    good_version = next(iter(SUPPORTED_FIRMWARE_VERSIONS))
    mock_robohat = MagicMock()
    mock_robohat.status.serial_connected = True
    mock_robohat.status.firmware_version = good_version
    mock_robohat.status.last_error = "pwm_ack_timeout"
    mock_robohat.send_motor_command = AsyncMock(return_value=False)
    gw._robohat = mock_robohat

    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.3, right=0.3, source="manual", duration_ms=200)
    )
    assert outcome.status == CommandStatus.ACK_FAILED
    assert outcome.watchdog_latency_ms is not None


# -- Observability event tests (W1-5) --

def _make_gw_with_store(mode: str = "full"):
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode

    safety = {"emergency_stop_active": False, "estop_reason": None}
    blade = {"active": False}
    client_em: dict = {}
    rest_mock = MagicMock()
    rest_mock._emergency_until = 0.0
    emitted = []
    store = EventStore(persistence=None, mode=PersistenceMode(mode))
    store.emit = lambda evt: emitted.append(evt)

    gw = MotorCommandGateway(
        safety_state=safety,
        blade_state=blade,
        client_emergency=client_em,
        robohat=None,
        persistence=None,
        _rest_module=rest_mock,
    )
    gw.set_event_store(store, run_id="run-gw", mission_id="m-gw")
    return gw, emitted


@pytest.mark.asyncio
async def test_dispatch_drive_emits_motion_command_issued(monkeypatch):
    from backend.src.control.commands import DriveCommand
    monkeypatch.setenv("SIM_MODE", "1")
    gw, emitted = _make_gw_with_store()
    cmd = DriveCommand(left=0.5, right=0.5, source="mission", duration_ms=500)
    await gw.dispatch_drive(cmd)
    issued = [e for e in emitted if e.event_type == "motion_command_issued"]
    assert len(issued) == 1
    assert issued[0].left == pytest.approx(0.5)
    assert issued[0].source == "mission"


@pytest.mark.asyncio
async def test_dispatch_drive_blocked_emits_safety_gate_blocked():
    from backend.src.control.commands import DriveCommand
    gw, emitted = _make_gw_with_store()
    gw._safety_state["emergency_stop_active"] = True
    cmd = DriveCommand(left=0.5, right=0.5, source="manual", duration_ms=200)
    await gw.dispatch_drive(cmd)
    blocked = [e for e in emitted if e.event_type == "safety_gate_blocked"]
    assert len(blocked) == 1
    assert blocked[0].reason == "emergency_stop_active"


@pytest.mark.asyncio
async def test_mission_drive_blocks_without_operating_area_in_hardware_mode(monkeypatch):
    from backend.src.control.commands import CommandStatus, DriveCommand

    monkeypatch.setenv("SIM_MODE", "0")
    gw, _, _ = _make_gw()

    outcome = await gw.dispatch_drive(
        DriveCommand(left=0.2, right=0.2, source="mission", duration_ms=200)
    )

    assert outcome.status == CommandStatus.BLOCKED
    assert outcome.status_reason == "SAFE_BOUNDARY_REQUIRED"


@pytest.mark.asyncio
async def test_heading_bootstrap_uses_bounded_isotropic_gateway_check() -> None:
    from backend.src.control.commands import DriveCommand

    snapshot = MagicMock(valid=True)
    snapshot.contains_footprint.return_value = True
    position = SimpleNamespace(accuracy=0.03)
    gw, _, _ = _make_gw()
    gw.set_autonomy_context_provider(
        lambda _cmd: {
            "snapshot": snapshot,
            "position": position,
            "last_gps_fix": object(),
            "dead_reckoning_active": False,
            "max_fix_age_s": 2.0,
            "max_accuracy_m": 0.25,
            "footprint_radius_m": 0.35,
            "fixed_allowance_m": 0.10,
            "accuracy_m": 0.03,
            "heading": None,
            "imu_valid": True,
            "imu_epoch_valid": True,
            "imu_age_s": 0.10,
            "heading_bootstrap_active": True,
            "mission_phase": "heading_bootstrap",
            "bootstrap_travel_m": 0.0,
            "bootstrap_remaining_m": 0.60,
            "bootstrap_stop_reserve_m": 0.15,
            "bootstrap_max_travel_m": 0.60,
            "bootstrap_imu_yaw_delta_deg": 0.0,
            "bootstrap_max_yaw_delta_deg": 15.0,
            "antenna_offset_m": 0.46,
            "tof_blocked": False,
        }
    )

    interlocks = await gw._check_mission_drive_interlocks(
        DriveCommand(
            left=0.2,
            right=0.2,
            source="mission",
            duration_ms=350,
            heading_bootstrap=True,
        )
    )

    assert interlocks == []
    snapshot.contains_footprint.assert_called_once_with(position, pytest.approx(1.54))
    snapshot.swept_motion_is_safe.assert_not_called()


@pytest.mark.asyncio
async def test_heading_bootstrap_gateway_rejects_invalid_imu_or_turn() -> None:
    from backend.src.control.commands import DriveCommand

    snapshot = MagicMock(valid=True)
    snapshot.contains_footprint.return_value = True
    context = {
        "snapshot": snapshot,
        "position": SimpleNamespace(accuracy=0.03),
        "last_gps_fix": object(),
        "dead_reckoning_active": False,
        "max_fix_age_s": 2.0,
        "max_accuracy_m": 0.25,
        "footprint_radius_m": 0.35,
        "fixed_allowance_m": 0.10,
        "accuracy_m": 0.03,
        "heading": None,
        "imu_valid": False,
        "imu_epoch_valid": True,
        "imu_age_s": 0.10,
        "heading_bootstrap_active": True,
        "mission_phase": "heading_bootstrap",
        "bootstrap_travel_m": 0.0,
        "bootstrap_remaining_m": 0.60,
        "bootstrap_stop_reserve_m": 0.15,
        "bootstrap_max_travel_m": 0.60,
        "bootstrap_imu_yaw_delta_deg": 0.0,
        "bootstrap_max_yaw_delta_deg": 15.0,
        "antenna_offset_m": 0.0,
        "tof_blocked": False,
    }
    gw, _, _ = _make_gw()
    gw.set_autonomy_context_provider(lambda _cmd: context)

    invalid_imu = await gw._check_mission_drive_interlocks(
        DriveCommand(
            left=0.2,
            right=0.2,
            source="mission",
            duration_ms=350,
            heading_bootstrap=True,
        )
    )
    context["imu_valid"] = True
    context["imu_epoch_valid"] = False
    invalid_epoch = await gw._check_mission_drive_interlocks(
        DriveCommand(
            left=0.2,
            right=0.2,
            source="mission",
            duration_ms=350,
            heading_bootstrap=True,
        )
    )
    context["imu_epoch_valid"] = True
    turning = await gw._check_mission_drive_interlocks(
        DriveCommand(
            left=0.2,
            right=0.1,
            source="mission",
            duration_ms=350,
            heading_bootstrap=True,
        )
    )

    assert "imu_not_ready" in invalid_imu
    assert "imu_not_ready" in invalid_epoch
    assert "heading_bootstrap_invalid" in turning


@pytest.mark.asyncio
async def test_headingless_untagged_mission_command_never_uses_bootstrap_exception() -> None:
    from backend.src.control.commands import DriveCommand

    snapshot = MagicMock(valid=True)
    snapshot.swept_motion_is_safe.return_value = False
    context = {
        "snapshot": snapshot,
        "position": SimpleNamespace(accuracy=0.03),
        "last_gps_fix": object(),
        "dead_reckoning_active": False,
        "max_fix_age_s": 2.0,
        "max_accuracy_m": 0.25,
        "footprint_radius_m": 0.35,
        "fixed_allowance_m": 0.10,
        "accuracy_m": 0.03,
        "heading": None,
        "heading_bootstrap_active": True,
        "mission_phase": "heading_bootstrap",
        "tof_blocked": False,
    }
    gw, _, _ = _make_gw()
    gw.set_autonomy_context_provider(lambda _cmd: context)

    interlocks = await gw._check_mission_drive_interlocks(
        DriveCommand(left=0.2, right=0.2, source="mission", duration_ms=350)
    )

    assert "geofence_prediction_blocked" in interlocks
    snapshot.contains_footprint.assert_not_called()


@pytest.mark.asyncio
async def test_heading_bootstrap_rejects_stale_imu_and_exhausted_stop_budget() -> None:
    from backend.src.control.commands import DriveCommand

    snapshot = MagicMock(valid=True)
    snapshot.contains_footprint.return_value = True
    context = {
        "snapshot": snapshot,
        "position": SimpleNamespace(accuracy=0.03),
        "last_gps_fix": object(),
        "dead_reckoning_active": False,
        "max_fix_age_s": 2.0,
        "max_accuracy_m": 0.25,
        "footprint_radius_m": 0.35,
        "fixed_allowance_m": 0.10,
        "accuracy_m": 0.03,
        "heading": None,
        "imu_valid": True,
        "imu_epoch_valid": True,
        "imu_age_s": 0.36,
        "heading_bootstrap_active": True,
        "mission_phase": "heading_bootstrap",
        "bootstrap_travel_m": 0.46,
        "bootstrap_remaining_m": 0.14,
        "bootstrap_stop_reserve_m": 0.15,
        "bootstrap_max_travel_m": 0.60,
        "bootstrap_imu_yaw_delta_deg": 0.0,
        "bootstrap_max_yaw_delta_deg": 15.0,
        "antenna_offset_m": 0.0,
        "tof_blocked": False,
    }
    gw, _, _ = _make_gw()
    gw.set_autonomy_context_provider(lambda _cmd: context)

    interlocks = await gw._check_mission_drive_interlocks(
        DriveCommand(
            left=0.2,
            right=0.2,
            source="mission",
            duration_ms=350,
            heading_bootstrap=True,
        )
    )

    assert "imu_not_ready" in interlocks
    assert "heading_bootstrap_budget_exhausted" in interlocks
    snapshot.contains_footprint.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_drive_in_summary_mode_does_not_persist_issued(monkeypatch):
    """In summary mode, MotionCommandIssued is not written to DB."""
    import os
    import tempfile

    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.control.commands import DriveCommand
    from backend.src.core.persistence import PersistenceLayer
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode

    written = []

    class SpyStore(EventStore):
        def _write(self, event):
            written.append(event)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    try:
        store = SpyStore(persistence=PersistenceLayer(db), mode=PersistenceMode.SUMMARY)

        rest_mock = MagicMock()
        rest_mock._emergency_until = 0.0
        gw = MotorCommandGateway(
            safety_state={"emergency_stop_active": False, "estop_reason": None},
            blade_state={"active": False},
            client_emergency={},
            robohat=None,
            persistence=None,
            _rest_module=rest_mock,
        )
        gw.set_event_store(store, run_id="r", mission_id="m")
        monkeypatch.setenv("SIM_MODE", "1")
        cmd = DriveCommand(left=0.1, right=0.1, source="mission", duration_ms=100)
        await gw.dispatch_drive(cmd)
        assert all(e.event_type != "motion_command_issued" for e in written)
    finally:
        os.unlink(db)
