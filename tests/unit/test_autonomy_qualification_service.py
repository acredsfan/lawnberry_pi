from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.src.models.autonomy_qualification import (
    AutonomyQualificationRecord,
    AutonomyQualificationStageResult,
    QualificationStageStatus,
)
from backend.src.services import autonomy_qualification_service as qualification_module
from backend.src.services.autonomy_qualification_service import (
    BLADE_ENABLED_REQUIRED_STAGES,
    PHYSICAL_EVIDENCE_STAGES,
    AutonomyQualificationError,
    AutonomyQualificationService,
)


class _Dumpable:
    def __init__(self, payload: dict):
        self._payload = payload

    def model_dump(self, *, mode: str = "json"):
        return self._payload


def _service(tmp_path, monkeypatch) -> AutonomyQualificationService:
    monkeypatch.setenv("SIM_MODE", "0")
    monkeypatch.setenv("LAWNBERRY_PLATFORM_MODEL", "Raspberry Pi 5 Model B Rev 1.0")
    monkeypatch.setattr(
        qualification_module,
        "_git_output",
        lambda root_dir, *args: "a1d01df07fe4bbb7868b951bd92758971afa9a48",
    )
    monkeypatch.setattr(qualification_module, "_git_tree_dirty", lambda root_dir: False)

    hardware_path = tmp_path / "config" / "hardware.yaml"
    hardware_path.parent.mkdir(parents=True)
    hardware_path.write_text(
        "blade:\n  controller: ibt-4\n  api_key: should-be-redacted\n",
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        config_loader=SimpleNamespace(hardware_path=hardware_path),
        safety_limits=_Dumpable(
            {
                "max_speed": 0.35,
                "tof_obstacle_distance_meters": 0.5,
            }
        ),
        robohat=SimpleNamespace(
            status=SimpleNamespace(firmware_version="robohat-fw-test")
        ),
    )
    return AutonomyQualificationService(runtime, root_dir=tmp_path)


def _stages(stage_ids: tuple[str, ...] = BLADE_ENABLED_REQUIRED_STAGES):
    return [
        AutonomyQualificationStageResult(
            stage_id=stage_id,
            status=QualificationStageStatus.PASSED,
            summary=f"{stage_id} passed",
        )
        for stage_id in stage_ids
    ]


def _attach_physical_artifacts(
    service: AutonomyQualificationService,
    record,
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
        (registry / f"{artifact_id}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )


def test_missing_evidence_blocks_hazardous_operation(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    evaluation = service.evaluate()

    assert not evaluation.ok
    assert "QUALIFICATION_EVIDENCE_MISSING" in evaluation.reason_codes


def test_current_passing_evidence_validates(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
        operator_id="aaron",
    )
    _attach_physical_artifacts(service, record)

    service.save_record(record)

    evaluation = service.assert_current()
    assert evaluation.ok
    assert evaluation.record is not None
    assert evaluation.record.record_id == record.record_id


def test_context_mismatch_invalidates_saved_evidence(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
    )
    _attach_physical_artifacts(service, record)
    service.save_record(record)
    monkeypatch.setattr(
        qualification_module,
        "_git_output",
        lambda root_dir, *args: "newer-commit",
    )
    service._runtime.config_loader.hardware_path.write_text(
        "blade:\n  controller: different-controller\n",
        encoding="utf-8",
    )
    service._runtime.safety_limits._payload["max_speed"] = 0.2
    service._runtime.robohat.status.firmware_version = "newer-firmware"

    evaluation = service.evaluate()

    assert not evaluation.ok
    assert "QUALIFICATION_COMMIT_MISMATCH" in evaluation.reason_codes
    assert "QUALIFICATION_HARDWARE_CONFIG_MISMATCH" in evaluation.reason_codes
    assert "QUALIFICATION_LIMITS_MISMATCH" in evaluation.reason_codes
    assert "QUALIFICATION_FIRMWARE_MISMATCH" in evaluation.reason_codes


def test_failed_interrupted_or_missing_stage_blocks(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    stages = _stages(BLADE_ENABLED_REQUIRED_STAGES[:-2])
    stages.append(
        AutonomyQualificationStageResult(
            stage_id=BLADE_ENABLED_REQUIRED_STAGES[-2],
            status=QualificationStageStatus.INTERRUPTED,
            summary="operator cancelled",
        )
    )
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.INTERRUPTED,
        stages=stages,
    )
    service.save_record(record)

    evaluation = service.evaluate()

    assert not evaluation.ok
    assert "QUALIFICATION_EVIDENCE_INTERRUPTED" in evaluation.reason_codes
    assert "QUALIFICATION_STAGE_INTERRUPTED" in evaluation.reason_codes
    assert "QUALIFICATION_STAGE_MISSING" in evaluation.reason_codes


def test_passed_physical_record_cannot_be_saved_from_sim_or_dirty_tree(
    tmp_path,
    monkeypatch,
):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
    )

    record.sim_mode = True
    with pytest.raises(AutonomyQualificationError) as sim_error:
        service.save_record(record)
    assert "QUALIFICATION_SIMULATION_MODE" in sim_error.value.evaluation.reason_codes

    record.sim_mode = False
    record.git_tree_dirty = True
    with pytest.raises(AutonomyQualificationError) as dirty_error:
        service.save_record(record)
    assert "QUALIFICATION_GIT_TREE_DIRTY" in dirty_error.value.evaluation.reason_codes


def test_passed_record_requires_retained_physical_stage_artifacts(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
    )

    with pytest.raises(AutonomyQualificationError) as error:
        service.save_record(record)

    assert "QUALIFICATION_STAGE_ARTIFACT_MISSING" in error.value.evaluation.reason_codes


def test_artifact_metadata_must_match_server_observed_context(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
    )
    _attach_physical_artifacts(service, record)
    artifact_id = record.artifact_ids[0]
    artifact_path = service.records_dir.parent / "registry" / f"{artifact_id}.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["metadata"]["commit_sha"] = "fabricated-commit"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AutonomyQualificationError) as error:
        service.save_record(record)

    assert "QUALIFICATION_STAGE_ARTIFACT_INVALID" in error.value.evaluation.reason_codes


def test_client_flags_cannot_override_live_simulation_context(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
    )
    record.sim_mode = False
    _attach_physical_artifacts(service, record)
    monkeypatch.setenv("SIM_MODE", "1")

    with pytest.raises(AutonomyQualificationError) as error:
        service.save_record(record)

    assert "QUALIFICATION_SIMULATION_MODE" in error.value.evaluation.reason_codes


def test_qualification_record_files_are_immutable(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    record = service.build_record_from_current_context(
        status=QualificationStageStatus.PASSED,
        stages=_stages(),
    )
    _attach_physical_artifacts(service, record)
    service.save_record(record)

    with pytest.raises(AutonomyQualificationError) as error:
        service.save_record(record)

    assert "QUALIFICATION_RECORD_EXISTS" in error.value.evaluation.reason_codes


@pytest.mark.parametrize("unsafe_id", ["../escape", "nested/path", "..", "/absolute"])
def test_evidence_identifiers_cannot_escape_storage_directory(unsafe_id):
    with pytest.raises(ValidationError):
        AutonomyQualificationRecord(
            record_id=unsafe_id,
            runtime_identity_hash="runtime-hash",
            hostname_hash="host-hash",
        )

    with pytest.raises(ValidationError):
        AutonomyQualificationStageResult(
            stage_id="static_config",
            status=QualificationStageStatus.PASSED,
            artifact_ids=[unsafe_id],
        )
