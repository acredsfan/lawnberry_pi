"""Adversarial fail-closed contracts for schema-v2 blade qualification."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.src.control.command_gateway import MotorCommandGateway
from backend.src.control.commands import (
    BladeCommand,
    CommandStatus,
    DriveCommand,
    EmergencyTrigger,
    SupervisedQualificationCommandContext,
)
from backend.src.models.autonomy_qualification import (
    QUALIFICATION_SCHEMA_VERSION,
    AutonomyQualificationStageResult,
    QualificationLevel,
    QualificationStageStatus,
    SupervisedTestPermitState,
)
from backend.src.models.safety_limits import SafetyLimits
from backend.src.models.sensor_data import ImuReading, SensorData, TofReading
from backend.src.safety.live_safety_coordinator import LiveSafetyCoordinator
from backend.src.services import autonomy_qualification_service as qualification_module
from backend.src.services import jobs_service as jobs_service_module
from backend.src.services.autonomy_qualification_service import (
    BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES,
    FULL_BLADE_AUTONOMY_REQUIRED_STAGES,
    PHYSICAL_EVIDENCE_STAGES,
    SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES,
    AutonomyQualificationError,
    AutonomyQualificationService,
    SupervisedTestPermitError,
)
from backend.src.services.jobs_service import JobsService, _JobAdmissionBlocked
from scripts import run_autonomy_qualification as qualification_runner

EXPECTED_PREREQUISITE_STAGES = (
    "static_config",
    "service_neutral",
    "sensor_freshness",
    "wheels_raised_drive",
    "failsafe_shutdown",
    "stationary_rtk_geofence",
    "blade_off_motion",
    "straight_line_cross_track",
    "obstacle_stop",
    "mission_scheduler_recovery",
    "webui_network_recovery",
    "cleanup",
)


class _Clock:
    def __init__(self) -> None:
        self.monotonic_value = 100.0
        self.wall_value = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.monotonic_value

    def wall(self) -> datetime:
        return self.wall_value

    def advance(self, seconds: float) -> None:
        self.monotonic_value += seconds
        self.wall_value += timedelta(seconds=seconds)


class _Limits:
    def __init__(self) -> None:
        self.supervised_test_enabled = True
        self.supervised_test_permit_ttl_s = 10
        self.supervised_test_max_duration_s = 20
        self.supervised_test_max_speed_mps = 0.20
        self.autonomous_command_ttl_ms = 350

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        del mode
        return vars(self).copy()


def _service(tmp_path, monkeypatch, *, clock: _Clock | None = None):
    monkeypatch.setenv("SIM_MODE", "0")
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    monkeypatch.setattr(
        qualification_module,
        "_git_output",
        lambda root_dir, *args: "08867b5c1282b988c0b717f81161987ba19ec8cb",
    )
    monkeypatch.setattr(qualification_module, "_git_tree_dirty", lambda root_dir: False)
    hardware_path = tmp_path / "config" / "hardware.yaml"
    hardware_path.parent.mkdir(parents=True, exist_ok=True)
    hardware_path.write_text("blade:\n  controller: ibt-4\n", encoding="utf-8")
    limits = _Limits()
    runtime = SimpleNamespace(
        config_loader=SimpleNamespace(hardware_path=hardware_path),
        hardware_config=None,
        safety_limits=limits,
        navigation=SimpleNamespace(max_speed=0.8),
        robohat=SimpleNamespace(status=SimpleNamespace(firmware_version="10.0.0")),
        persistence=SimpleNamespace(add_audit_log=lambda *args, **kwargs: None),
    )
    clock = clock or _Clock()
    service = AutonomyQualificationService(
        runtime,
        root_dir=tmp_path,
        monotonic=clock.monotonic,
        wall_clock=clock.wall,
    )
    return service, runtime, clock


def _passed_stages(stage_ids: tuple[str, ...]):
    return [
        AutonomyQualificationStageResult(
            stage_id=stage_id,
            status=QualificationStageStatus.PASSED,
            summary=f"{stage_id} passed",
        )
        for stage_id in stage_ids
    ]


def _attach_physical_artifacts(
    service,
    record,
    *,
    supervised_receipt_id: str | None = None,
    prefix: str = "artifact",
) -> None:
    context = service.build_context()
    registry = service.records_dir.parent / "registry"
    registry.mkdir(parents=True, exist_ok=True)
    for stage in record.stages:
        if stage.stage_id not in PHYSICAL_EVIDENCE_STAGES:
            continue
        artifact_id = f"{prefix}-{stage.stage_id}"
        stage.artifact_ids = [artifact_id]
        record.artifact_ids.append(artifact_id)
        payload = {
            "artifact_id": artifact_id,
            "metadata": {
                "qualification_stage_id": stage.stage_id,
                "commit_sha": context.commit_sha,
                "hardware_config_hash": context.hardware_config_hash,
                "limits_hash": context.limits_hash,
                "runtime_identity_hash": context.runtime_identity_hash,
                "robohat_firmware_version": context.robohat_firmware_version,
                "result": "passed",
                "operator_confirmed": True,
            },
        }
        if stage.stage_id == "supervised_blade_enabled":
            payload["metadata"]["supervised_test_receipt_id"] = supervised_receipt_id
        (registry / f"{artifact_id}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )


def _save_prerequisite(service):
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE,
        stages=_passed_stages(SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES),
        operator_id="aaron",
    )
    _attach_physical_artifacts(service, record)
    service.save_record(record)
    return record


def _issue(service, *, session: str = "operator-session"):
    return service.issue_supervised_test_permit(
        operator_id="aaron",
        operator_session_id=session,
        operator_confirmed=True,
        local_supervision_confirmed=True,
        physical_intervention_mechanism="verified master cutoff within immediate reach",
    )


def test_stage_sets_are_exact_and_camera_ai_remains_advisory():
    assert QUALIFICATION_SCHEMA_VERSION == 2
    assert BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES == (
        "static_config",
        "service_neutral",
        "sensor_freshness",
    )
    assert SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES == EXPECTED_PREREQUISITE_STAGES
    assert FULL_BLADE_AUTONOMY_REQUIRED_STAGES == (
        *EXPECTED_PREREQUISITE_STAGES,
        "supervised_blade_enabled",
    )
    assert "supervised_blade_enabled" in PHYSICAL_EVIDENCE_STAGES
    assert "camera_ai_degradation" not in SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES
    assert "camera_ai_degradation" not in FULL_BLADE_AUTONOMY_REQUIRED_STAGES


def test_runner_never_carries_schema_v1_stages_into_schema_v2(monkeypatch):
    context = {
        "schema_version": 2,
        "commit_sha": "08867b5c1282b988c0b717f81161987ba19ec8cb",
        "git_tree_dirty": False,
        "hardware_config_hash": "hardware-hash",
        "limits_hash": "limits-hash",
        "runtime_identity_hash": "runtime-hash",
        "pi_model": "Raspberry Pi 5",
        "hostname_hash": "hostname-hash",
        "machine_id_hash": "machine-hash",
        "os_release": "Raspberry Pi OS",
        "sim_mode": False,
        "robohat_firmware_version": "10.0.0",
    }
    schema_v1_record = {
        **context,
        "schema_version": 1,
        "stages": [
            {
                "stage_id": stage_id,
                "status": "passed",
                "summary": "historical schema-v1 pass",
            }
            for stage_id in BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES
        ],
    }

    class _ApiClient:
        def __init__(self, base_url: str, timeout_s: float):
            del base_url, timeout_s

        def get(self, path: str):
            assert path == "/api/v2/autonomy/qualification"
            return {
                "context": context,
                "record": schema_v1_record,
                "reason_codes": ["QUALIFICATION_SCHEMA_MISMATCH"],
            }

        def post(self, path: str, payload: dict):
            del path, payload
            return {}

    monkeypatch.setattr(qualification_runner, "ApiClient", _ApiClient)
    args = SimpleNamespace(
        base_url="http://127.0.0.1:8081",
        timeout_s=1.0,
        stage=["wheels_raised_drive"],
        stage_result=["wheels_raised_drive=passed"],
        artifact_id=["wheels_raised_drive=artifact-new"],
        physical_intervention="verified master cutoff",
        fresh=False,
        operator_confirmed=True,
        operator="aaron",
        notes="schema migration regression",
        store=False,
    )

    record = qualification_runner.run(args)
    stage = next(
        item for item in record.stages if item.stage_id == "wheels_raised_drive"
    )

    assert record.schema_version == 2
    assert stage.status == QualificationStageStatus.FAILED
    assert stage.reason_code == "STAGE_PREREQUISITE_MISSING"
    assert not any(
        item.summary == "historical schema-v1 pass" for item in record.stages
    )


@pytest.mark.parametrize(
    "operator_confirmed,local_confirmed,intervention",
    [
        (False, True, "verified master cutoff within reach"),
        (True, False, "verified master cutoff within reach"),
        (True, True, "cutoff"),
    ],
)
def test_permit_requires_every_operator_supervision_confirmation(
    tmp_path,
    monkeypatch,
    operator_confirmed,
    local_confirmed,
    intervention,
):
    service, _, _ = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)

    with pytest.raises(SupervisedTestPermitError) as denied:
        service.issue_supervised_test_permit(
            operator_id="aaron",
            operator_session_id="operator-session",
            operator_confirmed=operator_confirmed,
            local_supervision_confirmed=local_confirmed,
            physical_intervention_mechanism=intervention,
        )

    assert denied.value.reason_code == "SUPERVISED_TEST_OPERATOR_CONFIRMATION_REQUIRED"
    assert service.supervised_test_permit_status().state == SupervisedTestPermitState.ABSENT


def test_permit_denies_simulated_or_changed_context_and_revokes_after_drift(
    tmp_path,
    monkeypatch,
):
    service, runtime, _ = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)

    monkeypatch.setenv("SIM_MODE", "1")
    with pytest.raises(AutonomyQualificationError) as simulated:
        _issue(service)
    assert "QUALIFICATION_SIMULATION_MODE" in simulated.value.evaluation.reason_codes
    assert service.supervised_test_permit_status().state == SupervisedTestPermitState.ABSENT

    monkeypatch.setenv("SIM_MODE", "0")
    issued = _issue(service)
    service.activate_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="operator-session",
    )
    runtime.safety_limits.supervised_test_max_speed_mps = 0.19

    with pytest.raises(SupervisedTestPermitError) as drifted:
        service.authorize_supervised_command(
            permit_token=issued.permit_token,
            operator_session_id="operator-session",
            command_type="blade",
        )

    assert drifted.value.reason_code == "SUPERVISED_TEST_PERMIT_CONTEXT_MISMATCH"
    assert drifted.value.status.state == SupervisedTestPermitState.REVOKED


def test_schema_v1_prerequisite_cannot_issue_permit(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE,
        stages=_passed_stages(SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES),
    )
    _attach_physical_artifacts(service, record)
    record.schema_version = 1
    service.records_dir.mkdir(parents=True, exist_ok=True)
    service._latest_path.write_text(record.model_dump_json(), encoding="utf-8")

    with pytest.raises(AutonomyQualificationError) as denied:
        _issue(service)

    assert "QUALIFICATION_SCHEMA_MISMATCH" in denied.value.evaluation.reason_codes
    assert service.supervised_test_permit_status().state == SupervisedTestPermitState.ABSENT


def test_status_is_redacted_and_token_is_single_use(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)
    issued = _issue(service)
    token = issued.permit_token

    public_payload = service.supervised_test_permit_status().model_dump_json()
    assert token not in public_payload
    assert "master cutoff" not in public_payload
    assert "permit_token" not in public_payload

    service.activate_supervised_test_permit(
        permit_token=token,
        operator_session_id="operator-session",
    )
    with pytest.raises(SupervisedTestPermitError) as second_activation:
        service.activate_supervised_test_permit(
            permit_token=token,
            operator_session_id="operator-session",
        )
    assert second_activation.value.reason_code == "SUPERVISED_TEST_PERMIT_ALREADY_USED"

    completed = service.complete_supervised_test_permit(
        permit_token=token,
        operator_session_id="operator-session",
        cleanup_confirmed=True,
    )
    assert completed.state == SupervisedTestPermitState.COMPLETED
    with pytest.raises(SupervisedTestPermitError) as reused:
        service.authorize_supervised_command(
            permit_token=token,
            operator_session_id="operator-session",
            command_type="blade",
        )
    assert reused.value.reason_code == "SUPERVISED_TEST_PERMIT_ALREADY_USED"


def test_cleanup_receipt_can_be_claimed_by_only_one_full_record(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)
    issued = _issue(service)
    service.activate_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="operator-session",
    )
    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="operator-session",
        command_type="drive",
        left_normalized=0.1,
        right_normalized=0.1,
        duration_ms=100,
    )
    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="operator-session",
        command_type="blade",
    )
    completed = service.complete_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="operator-session",
        cleanup_confirmed=True,
        cleanup_evidence={
            "drive_audit_id": "drive-audit-accepted",
            "drive_status": "accepted",
            "blade_audit_id": "blade-audit-accepted",
            "blade_status": "accepted",
        },
    )
    assert completed.receipt_evidence_eligible is True

    first = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.FULL_BLADE_AUTONOMY,
        stages=_passed_stages(FULL_BLADE_AUTONOMY_REQUIRED_STAGES),
        operator_id="aaron",
    )
    _attach_physical_artifacts(
        service,
        first,
        supervised_receipt_id=completed.receipt_id,
        prefix="first",
    )
    service.save_record(first)

    second = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.FULL_BLADE_AUTONOMY,
        stages=_passed_stages(FULL_BLADE_AUTONOMY_REQUIRED_STAGES),
        operator_id="aaron",
    )
    _attach_physical_artifacts(
        service,
        second,
        supervised_receipt_id=completed.receipt_id,
        prefix="second",
    )

    with pytest.raises(AutonomyQualificationError) as reused:
        service.save_record(second)

    assert "SUPERVISED_TEST_RECEIPT_INVALID" in reused.value.evaluation.reason_codes
    assert not (service.records_dir / f"{second.record_id}.json").exists()


def test_concurrent_activation_consumes_issue_state_exactly_once(tmp_path, monkeypatch):
    service, _, _ = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)
    issued = _issue(service)
    barrier = threading.Barrier(3)

    def activate() -> str:
        barrier.wait()
        try:
            return service.activate_supervised_test_permit(
                permit_token=issued.permit_token,
                operator_session_id="operator-session",
            ).state
        except SupervisedTestPermitError as exc:
            return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(activate) for _ in range(2)]
        barrier.wait()
        results = [future.result(timeout=1.0) for future in futures]

    assert results.count(SupervisedTestPermitState.ACTIVE) == 1
    assert results.count("SUPERVISED_TEST_PERMIT_ALREADY_USED") == 1


class _PermitGateError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class _GatewayQualification:
    def __init__(self, *, active: bool = True, full_ok: bool = False) -> None:
        self.active = active
        self.full_ok = full_ok
        self.authorized: list[dict[str, object]] = []
        self.revocations: list[str] = []
        self.full_checks = 0
        self.state = SupervisedTestPermitState.ACTIVE if active else SupervisedTestPermitState.ABSENT

    def authorize_supervised_command(self, **kwargs):
        self.authorized.append(kwargs)

    def assert_supervised_test_inactive(self) -> None:
        if self.active:
            raise _PermitGateError("SUPERVISED_TEST_PERMIT_ACTIVE")

    def assert_current(self):
        self.full_checks += 1
        if not self.full_ok:
            exc = RuntimeError("full qualification required")
            exc.evaluation = SimpleNamespace(
                reason_codes=["SUPERVISED_BLADE_TEST_REQUIRED"]
            )
            raise exc

    def revoke_supervised_test_permit(self, reason_code: str):
        self.active = False
        self.state = (
            SupervisedTestPermitState.EXPIRED
            if reason_code == "SUPERVISED_TEST_PERMIT_EXPIRED"
            else SupervisedTestPermitState.REVOKED
        )
        self.revocations.append(reason_code)


class _BladeController:
    def __init__(self, *, initialize_ok: bool = True, command_ok: bool = True) -> None:
        self.initialize_ok = initialize_ok
        self.command_ok = command_ok
        self.commands: list[tuple[bool, str]] = []

    async def initialize(self) -> bool:
        return self.initialize_ok

    async def set_active(self, active: bool, *, reason: str):
        self.commands.append((active, reason))
        return SimpleNamespace(
            ok=self.command_ok,
            reason_code=None if self.command_ok else "BLADE_ACK_TIMEOUT",
        )

    async def emergency_stop(self, *, reason: str):
        self.commands.append((False, reason))
        return SimpleNamespace(ok=True)


def _gateway(
    *,
    qualification: _GatewayQualification | None = None,
    send_motor=None,
    blade_controller: _BladeController | None = None,
    lease_ms: int = 350,
):
    rest = SimpleNamespace(_emergency_until=0.0, _legacy_motors_active=False)
    robohat = SimpleNamespace(
        status=SimpleNamespace(
            serial_connected=True,
            firmware_version="10.0.0",
            last_error=None,
        ),
        send_motor_command=send_motor or AsyncMock(return_value=True),
        emergency_stop=AsyncMock(return_value=True),
        clear_emergency=AsyncMock(return_value=True),
    )
    loader = SimpleNamespace(
        get=lambda: (None, SimpleNamespace(autonomous_command_ttl_ms=lease_ms))
    )
    gateway = MotorCommandGateway(
        safety_state={"emergency_stop_active": False, "estop_reason": None},
        blade_state={"active": False},
        client_emergency={},
        robohat=robohat,
        persistence=SimpleNamespace(add_audit_log=lambda *args, **kwargs: None),
        config_loader=loader,
        _rest_module=rest,
    )
    qualification = qualification or _GatewayQualification()
    controller = blade_controller or _BladeController()
    gateway.set_qualification_service(qualification)
    gateway.set_blade_controller(controller)
    gateway._supervised_runtime_blockers = AsyncMock(return_value=[])
    gateway._supervised_pose_blockers = lambda cmd: []
    gateway._check_mission_drive_interlocks = AsyncMock(return_value=[])
    return gateway, qualification, robohat, controller


def _capability(token: str = "q" * 43):
    return SupervisedQualificationCommandContext(
        permit_token=token,
        operator_session_id="operator-session",
    )


@pytest.mark.asyncio
async def test_gateway_rejects_supervised_source_without_typed_capability_and_neutralizes():
    gateway, qualification, robohat, controller = _gateway()

    outcome = await gateway.dispatch_drive(
        DriveCommand(
            left=0.1,
            right=0.1,
            source="supervised_qualification",
            duration_ms=100,
        )
    )

    assert outcome.status == CommandStatus.BLOCKED
    assert outcome.status_reason == "SUPERVISED_TEST_COMMAND_SOURCE_INVALID"
    assert qualification.revocations == ["SUPERVISED_TEST_COMMAND_SOURCE_INVALID"]
    robohat.send_motor_command.assert_awaited_with(0.0, 0.0)
    assert controller.commands[-1][0] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["manual", "mission"])
async def test_ordinary_source_cannot_consume_forged_supervised_capability(source):
    qualification = _GatewayQualification(active=False, full_ok=False)
    gateway, qualification, robohat, _ = _gateway(qualification=qualification)

    if source == "manual":
        outcome = await gateway.dispatch_blade(
            BladeCommand(active=True, source=source, qualification=_capability())
        )
    else:
        outcome = await gateway.dispatch_blade(
            BladeCommand(active=True, source=source, qualification=_capability())
        )

    assert outcome.status == CommandStatus.BLOCKED
    assert "SUPERVISED_BLADE_TEST_REQUIRED" in (outcome.status_reason or "")
    assert qualification.authorized == []
    assert qualification.full_checks == 1
    robohat.send_motor_command.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["manual", "mission"])
async def test_active_permit_exclusively_blocks_ordinary_nonzero_drive(source):
    qualification = _GatewayQualification(active=True, full_ok=True)
    gateway, qualification, robohat, _ = _gateway(qualification=qualification)

    outcome = await gateway.dispatch_drive(
        DriveCommand(left=0.1, right=0.1, source=source, duration_ms=100)
    )

    assert outcome.status == CommandStatus.BLOCKED
    assert outcome.status_reason == "SUPERVISED_TEST_PERMIT_ACTIVE"
    assert qualification.authorized == []
    robohat.send_motor_command.assert_not_awaited()


@pytest.mark.asyncio
async def test_supervised_drive_ack_failure_neutralizes_and_revokes():
    send_motor = AsyncMock(side_effect=[False, True])
    gateway, qualification, _, controller = _gateway(send_motor=send_motor)

    outcome = await gateway.dispatch_drive(
        DriveCommand(
            left=0.1,
            right=0.1,
            source="supervised_qualification",
            duration_ms=100,
            qualification=_capability(),
        )
    )

    assert outcome.status == CommandStatus.ACK_FAILED
    assert qualification.revocations == ["SUPERVISED_TEST_DRIVE_ACK_FAILED"]
    assert send_motor.await_args_list[-1].args == (0.0, 0.0)
    assert controller.commands[-1][0] is False


@pytest.mark.asyncio
async def test_supervised_blade_controller_init_failure_neutralizes_and_revokes():
    controller = _BladeController(initialize_ok=False)
    gateway, qualification, robohat, _ = _gateway(blade_controller=controller)

    outcome = await gateway.dispatch_blade(
        BladeCommand(
            active=True,
            source="supervised_qualification",
            qualification=_capability(),
        )
    )

    assert outcome.status == CommandStatus.ACK_FAILED
    assert outcome.status_reason == "BLADE_CONTROLLER_OFFLINE"
    assert qualification.revocations == ["SUPERVISED_TEST_BLADE_CONTROLLER_OFFLINE"]
    robohat.send_motor_command.assert_awaited_with(0.0, 0.0)
    assert gateway._blade_state["active"] is False


@pytest.mark.asyncio
async def test_supervised_runtime_safety_blocker_neutralizes_and_revokes():
    gateway, qualification, robohat, controller = _gateway()
    gateway._supervised_runtime_blockers = AsyncMock(return_value=["TOF_LEFT_STALE"])

    outcome = await gateway.dispatch_drive(
        DriveCommand(
            left=0.1,
            right=0.1,
            source="supervised_qualification",
            duration_ms=100,
            qualification=_capability(),
        )
    )

    assert outcome.status == CommandStatus.BLOCKED
    assert outcome.status_reason == "TOF_LEFT_STALE"
    assert qualification.revocations == ["TOF_LEFT_STALE"]
    robohat.send_motor_command.assert_awaited_with(0.0, 0.0)
    assert controller.commands[-1][0] is False


@pytest.mark.asyncio
async def test_supervised_drive_lease_expiry_is_event_driven_neutral_and_revoke():
    stopped = asyncio.Event()
    calls: list[tuple[float, float]] = []

    async def send_motor(left: float, right: float) -> bool:
        calls.append((left, right))
        if (left, right) == (0.0, 0.0):
            stopped.set()
        return True

    gateway, qualification, _, controller = _gateway(
        send_motor=send_motor,
        lease_ms=5,
    )

    outcome = await gateway.dispatch_drive(
        DriveCommand(
            left=0.1,
            right=0.1,
            source="supervised_qualification",
            duration_ms=5,
            qualification=_capability(),
        )
    )
    assert outcome.status == CommandStatus.ACCEPTED

    await asyncio.wait_for(stopped.wait(), timeout=0.5)
    await asyncio.sleep(0)
    assert calls[-1] == (0.0, 0.0)
    assert qualification.revocations == ["SUPERVISED_TEST_COMMAND_LEASE_EXPIRED"]
    assert controller.commands[-1][0] is False


@pytest.mark.asyncio
async def test_permit_deadline_task_marks_expired_and_neutralizes_both_actuators():
    stopped = asyncio.Event()
    calls: list[tuple[float, float]] = []

    async def send_motor(left: float, right: float) -> bool:
        calls.append((left, right))
        if (left, right) == (0.0, 0.0):
            stopped.set()
        return True

    gateway, qualification, _, controller = _gateway(send_motor=send_motor)
    gateway._blade_state["active"] = True
    gateway.arm_supervised_permit_deadline(0.001)

    await asyncio.wait_for(stopped.wait(), timeout=0.5)
    await asyncio.sleep(0)

    assert qualification.state == SupervisedTestPermitState.EXPIRED
    assert qualification.revocations == ["SUPERVISED_TEST_PERMIT_EXPIRED"]
    assert calls[-1] == (0.0, 0.0)
    assert controller.commands[-1][0] is False
    assert gateway._blade_state["active"] is False


@pytest.mark.asyncio
async def test_emergency_stop_revokes_supervised_permit_and_keeps_outputs_safe():
    gateway, qualification, _, controller = _gateway()
    gateway._blade_state["active"] = True

    outcome = await gateway.trigger_emergency(
        EmergencyTrigger(reason="operator cutoff requested", source="operator")
    )

    assert outcome.status == CommandStatus.EMERGENCY_LATCHED
    assert qualification.revocations == ["SUPERVISED_TEST_EMERGENCY_STOP"]
    assert gateway._blade_state["active"] is False
    assert controller.commands[-1][0] is False


class _LiveSafetyQualification:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    def revoke_supervised_test_permit(self, reason: str) -> None:
        self.reasons.append(reason)


class _LiveSafetyGateway:
    def __init__(self) -> None:
        self.drive_commands: list[DriveCommand] = []
        self.blade_commands: list[BladeCommand] = []

    async def dispatch_drive(self, command):
        self.drive_commands.append(command)
        return SimpleNamespace(status="accepted")

    async def dispatch_blade(self, command):
        self.blade_commands.append(command)
        return SimpleNamespace(status="accepted")

    async def trigger_emergency(self, trigger):
        return SimpleNamespace(status="accepted")


@pytest.mark.asyncio
async def test_live_safety_fault_revokes_permit_after_commanding_neutral_and_blade_off():
    qualification = _LiveSafetyQualification()
    gateway = _LiveSafetyGateway()
    runtime = SimpleNamespace(
        safety_limits=SafetyLimits(),
        command_gateway=gateway,
        qualification_service=qualification,
        blade_state={"active": True},
        navigation=SimpleNamespace(
            navigation_state=SimpleNamespace(target_velocity=0.2)
        ),
        sensor_manager=None,
    )
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(
            imu=ImuReading(roll=0.0, pitch=0.0),
            tof_left=TofReading(
                sensor_side="left",
                distance=100.0,
                sample_id=1,
                monotonic_received_s=time.monotonic(),
            ),
            tof_right=TofReading(
                sensor_side="right",
                distance=1000.0,
                sample_id=1,
                monotonic_received_s=time.monotonic(),
            ),
        )
    )

    assert "OBSTACLE_STOP" in faults
    assert gateway.drive_commands[-1].left == 0.0
    assert gateway.drive_commands[-1].right == 0.0
    assert gateway.blade_commands[-1].active is False
    assert qualification.reasons == [
        "SUPERVISED_TEST_LIVE_SAFETY_FAULT:OBSTACLE_STOP"
    ]


class _SchedulerQualification:
    def __init__(self) -> None:
        self.full_checks = 0

    def assert_supervised_test_inactive(self) -> None:
        raise _PermitGateError("SUPERVISED_TEST_PERMIT_ACTIVE")

    def assert_current(self) -> None:
        self.full_checks += 1


class _SchedulerMissions:
    def __init__(self) -> None:
        self.mission_statuses = {}
        self.create_calls = 0

    async def list_missions(self):
        return []

    async def create_mission(self, **kwargs):
        self.create_calls += 1
        return SimpleNamespace(id="must-not-be-created")


@pytest.mark.asyncio
async def test_scheduler_admission_cannot_consume_active_supervised_permit(monkeypatch):
    monkeypatch.setattr(
        jobs_service_module,
        "get_safety_state",
        lambda: {"emergency_stop_active": False},
    )
    qualification = _SchedulerQualification()
    missions = _SchedulerMissions()
    service = JobsService()
    service.set_qualification_service(qualification)
    service.set_mission_service(missions)

    with pytest.raises(_JobAdmissionBlocked, match="SUPERVISED_TEST_PERMIT_ACTIVE"):
        await service._admit_job_mission(
            job_id="job-1",
            job_name="scheduled mow",
            zones=["zone-1"],
            pattern="parallel",
            pattern_params={},
            mission_name="scheduled mission",
        )

    assert qualification.full_checks == 0
    assert missions.create_calls == 0
