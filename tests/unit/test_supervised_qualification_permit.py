from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend.src.models.autonomy_qualification import (
    AutonomyQualificationStageResult,
    QualificationLevel,
    QualificationStageStatus,
    SupervisedTestPermitState,
)
from backend.src.services import autonomy_qualification_service as qualification_module
from backend.src.services.autonomy_qualification_service import (
    FULL_BLADE_AUTONOMY_REQUIRED_STAGES,
    PHYSICAL_EVIDENCE_STAGES,
    SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES,
    AutonomyQualificationError,
    AutonomyQualificationService,
    SupervisedTestPermitError,
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
    supervised_test_enabled = True
    supervised_test_permit_ttl_s = 10
    supervised_test_max_duration_s = 20
    supervised_test_max_speed_mps = 0.20
    autonomous_command_ttl_ms = 350

    def model_dump(self, *, mode: str = "json") -> dict:
        return {
            "supervised_test_enabled": self.supervised_test_enabled,
            "supervised_test_permit_ttl_s": self.supervised_test_permit_ttl_s,
            "supervised_test_max_duration_s": self.supervised_test_max_duration_s,
            "supervised_test_max_speed_mps": self.supervised_test_max_speed_mps,
            "autonomous_command_ttl_ms": self.autonomous_command_ttl_ms,
        }


def _service(tmp_path, monkeypatch, clock: _Clock | None = None) -> AutonomyQualificationService:
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
    runtime = SimpleNamespace(
        config_loader=SimpleNamespace(hardware_path=hardware_path),
        safety_limits=_Limits(),
        navigation=SimpleNamespace(max_speed=0.8),
        robohat=SimpleNamespace(status=SimpleNamespace(firmware_version="10.0.0")),
        persistence=SimpleNamespace(add_audit_log=lambda *args, **kwargs: None),
    )
    clock = clock or _Clock()
    return AutonomyQualificationService(
        runtime,
        root_dir=tmp_path,
        monotonic=clock.monotonic,
        wall_clock=clock.wall,
    )


def _write_stage_artifacts(
    service: AutonomyQualificationService,
    record,
    *,
    supervised_receipt_id: str | None = None,
) -> None:
    context = service.build_context()
    registry = service.records_dir.parent / "registry"
    registry.mkdir(parents=True, exist_ok=True)
    for stage in record.stages:
        if stage.stage_id not in PHYSICAL_EVIDENCE_STAGES:
            continue
        artifact_id = f"artifact-{stage.stage_id}"
        stage.artifact_ids = [artifact_id]
        record.artifact_ids.append(artifact_id)
        metadata = {
            "qualification_stage_id": stage.stage_id,
            "commit_sha": context.commit_sha,
            "hardware_config_hash": context.hardware_config_hash,
            "limits_hash": context.limits_hash,
            "runtime_identity_hash": context.runtime_identity_hash,
            "robohat_firmware_version": context.robohat_firmware_version,
            "result": "passed",
            "operator_confirmed": True,
        }
        if stage.stage_id == "supervised_blade_enabled":
            metadata["supervised_test_receipt_id"] = supervised_receipt_id
        (registry / f"{artifact_id}.json").write_text(
            json.dumps({"artifact_id": artifact_id, "metadata": metadata}),
            encoding="utf-8",
        )


def _passed_stages(stage_ids: tuple[str, ...]) -> list[AutonomyQualificationStageResult]:
    return [
        AutonomyQualificationStageResult(
            stage_id=stage_id,
            status=QualificationStageStatus.PASSED,
            summary=f"{stage_id} passed",
        )
        for stage_id in stage_ids
    ]


def _save_prerequisite(service: AutonomyQualificationService):
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE,
        stages=_passed_stages(SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES),
        operator_id="aaron",
    )
    _write_stage_artifacts(service, record)
    service.save_record(record)
    return record


def _issue(service: AutonomyQualificationService):
    return service.issue_supervised_test_permit(
        operator_id="aaron",
        operator_session_id="auth-session-1",
        operator_confirmed=True,
        local_supervision_confirmed=True,
        physical_intervention_mechanism="verified master power cutoff within reach",
    )


def test_prerequisite_level_cannot_authorize_full_blade_autonomy(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = _save_prerequisite(service)

    prerequisite = service.assert_prerequisite_current()
    full = service.evaluate()

    assert prerequisite.ok
    assert prerequisite.record.record_id == record.record_id
    assert full.prerequisite_ok is True
    assert full.full_autonomy_ok is False
    assert "SUPERVISED_BLADE_TEST_REQUIRED" in full.reason_codes
    with pytest.raises(AutonomyQualificationError):
        service.assert_current()


def test_schema_v1_record_is_history_only_and_fails_closed(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.FULL_BLADE_AUTONOMY,
        stages=_passed_stages(FULL_BLADE_AUTONOMY_REQUIRED_STAGES),
    )
    record.schema_version = 1
    service.records_dir.mkdir(parents=True, exist_ok=True)
    service._latest_path.write_text(record.model_dump_json(), encoding="utf-8")

    evaluation = service.evaluate()

    assert not evaluation.ok
    assert "QUALIFICATION_SCHEMA_MISMATCH" in evaluation.reason_codes


def test_permit_is_single_session_bound_and_polling_does_not_extend_it(tmp_path, monkeypatch):
    clock = _Clock()
    service = _service(tmp_path, monkeypatch, clock)
    _save_prerequisite(service)

    issued = _issue(service)
    issued_expiry = issued.status.expires_at
    with pytest.raises(SupervisedTestPermitError) as duplicate:
        _issue(service)
    assert duplicate.value.reason_code == "SUPERVISED_TEST_PERMIT_ALREADY_EXISTS"

    active = service.activate_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
    )
    assert active.state == SupervisedTestPermitState.ACTIVE

    clock.advance(2)
    polled = service.supervised_test_permit_status()
    assert polled.state == SupervisedTestPermitState.ACTIVE
    assert polled.expires_at != issued_expiry
    remaining_after_first_poll = polled.remaining_seconds
    clock.advance(2)
    assert service.supervised_test_permit_status().remaining_seconds < remaining_after_first_poll

    with pytest.raises(SupervisedTestPermitError) as wrong_session:
        service.authorize_supervised_command(
            permit_token=issued.permit_token,
            operator_session_id="different-session",
            command_type="blade",
        )
    assert wrong_session.value.reason_code == "SUPERVISED_TEST_PERMIT_SESSION_MISMATCH"

    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        command_type="drive",
        left_normalized=0.20,
        right_normalized=0.20,
        duration_ms=300,
    )

    restarted = _service(tmp_path, monkeypatch, clock)
    assert restarted.supervised_test_permit_status().state == SupervisedTestPermitState.ABSENT


def test_permit_expires_and_rejects_excess_speed(tmp_path, monkeypatch):
    clock = _Clock()
    service = _service(tmp_path, monkeypatch, clock)
    _save_prerequisite(service)
    issued = _issue(service)
    service.activate_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
    )

    with pytest.raises(SupervisedTestPermitError) as speed_error:
        service.authorize_supervised_command(
            permit_token=issued.permit_token,
            operator_session_id="auth-session-1",
            command_type="drive",
            left_normalized=0.5,
            right_normalized=0.5,
            duration_ms=300,
        )
    assert speed_error.value.reason_code == "SUPERVISED_TEST_SPEED_LIMIT_EXCEEDED"

    clock.advance(21)
    with pytest.raises(SupervisedTestPermitError) as expired:
        service.authorize_supervised_command(
            permit_token=issued.permit_token,
            operator_session_id="auth-session-1",
            command_type="blade",
        )
    assert expired.value.reason_code == "SUPERVISED_TEST_PERMIT_EXPIRED"
    assert service.supervised_test_permit_status().state == SupervisedTestPermitState.EXPIRED


def test_concurrent_issue_creates_exactly_one_permit(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)

    def attempt_issue() -> str:
        try:
            return _issue(service).status.state
        except SupervisedTestPermitError as exc:
            return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt_issue(), range(2)))

    assert results.count(SupervisedTestPermitState.ISSUED) == 1
    assert results.count("SUPERVISED_TEST_PERMIT_ALREADY_EXISTS") == 1


def test_permit_audit_binds_context_without_recording_reusable_secrets(
    tmp_path,
    monkeypatch,
):
    service = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)
    audit_events: list[tuple[str, dict]] = []
    service._runtime.persistence.add_audit_log = (  # noqa: SLF001 - isolated audit seam
        lambda action, *, details: audit_events.append((action, details))
    )

    issued = _issue(service)

    action, details = audit_events[-1]
    serialized = json.dumps(audit_events)
    assert action == "qualification.supervised_permit.issued"
    assert details["commit_sha"]
    assert details["hardware_config_hash"]
    assert details["limits_hash"]
    assert details["runtime_identity_hash"]
    assert details["physical_intervention_mechanism_hash"]
    assert issued.permit_token not in serialized
    assert "verified master cutoff" not in serialized.lower()


def test_current_full_qualification_cannot_issue_an_unnecessary_permit(
    tmp_path,
    monkeypatch,
):
    service = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)
    issued = _issue(service)
    service.activate_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
    )
    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        command_type="drive",
        left_normalized=0.2,
        right_normalized=0.2,
        duration_ms=300,
    )
    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        command_type="blade",
    )
    completed = service.complete_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        cleanup_confirmed=True,
        cleanup_evidence={
            "drive_audit_id": "drive-audit",
            "drive_status": "accepted",
            "blade_audit_id": "blade-audit",
            "blade_status": "accepted",
        },
    )
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.FULL_BLADE_AUTONOMY,
        stages=_passed_stages(FULL_BLADE_AUTONOMY_REQUIRED_STAGES),
        operator_id="aaron",
    )
    _write_stage_artifacts(service, record, supervised_receipt_id=completed.receipt_id)
    service.save_record(record)

    with pytest.raises(SupervisedTestPermitError) as exc_info:
        _issue(service)

    assert exc_info.value.reason_code == "SUPERVISED_TEST_FULL_QUALIFICATION_CURRENT"


def test_full_evidence_requires_server_receipt_with_confirmed_cleanup(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    _save_prerequisite(service)
    issued = _issue(service)
    service.activate_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
    )
    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        command_type="drive",
        left_normalized=0.2,
        right_normalized=0.2,
        duration_ms=300,
    )
    service.authorize_supervised_command(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        command_type="blade",
    )
    completed = service.complete_supervised_test_permit(
        permit_token=issued.permit_token,
        operator_session_id="auth-session-1",
        cleanup_confirmed=True,
        cleanup_evidence={
            "drive_audit_id": "drive-audit",
            "drive_status": "accepted",
            "blade_audit_id": "blade-audit",
            "blade_status": "accepted",
        },
    )
    assert completed.state == SupervisedTestPermitState.COMPLETED
    assert completed.receipt_id
    receipt = json.loads(
        (service.receipts_dir / f"{completed.receipt_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(receipt["physical_intervention_mechanism_hash"]) == 64
    assert "master cutoff" not in json.dumps(receipt).lower()

    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        qualification_level=QualificationLevel.FULL_BLADE_AUTONOMY,
        stages=_passed_stages(FULL_BLADE_AUTONOMY_REQUIRED_STAGES),
        operator_id="aaron",
    )
    _write_stage_artifacts(
        service,
        record,
        supervised_receipt_id=completed.receipt_id,
    )
    service.save_record(record)

    assert service.assert_current().ok
