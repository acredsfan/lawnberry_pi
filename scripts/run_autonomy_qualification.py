#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from backend.src.models.autonomy_qualification import (
    AutonomyQualificationRecord,
    AutonomyQualificationStageResult,
    QualificationStageStatus,
)
from backend.src.services.autonomy_qualification_service import (
    BLADE_ENABLED_REQUIRED_STAGES,
)

NON_DESTRUCTIVE_STAGES = ("static_config", "service_neutral", "sensor_freshness")
HAZARDOUS_STAGES = (
    "wheels_raised_drive",
    "failsafe_shutdown",
    "stationary_rtk_geofence",
    "blade_off_motion",
    "straight_line_cross_track",
    "obstacle_stop",
    "mission_scheduler_recovery",
    "camera_ai_degradation",
    "webui_network_recovery",
    "supervised_blade_enabled",
)
ALL_STAGES = NON_DESTRUCTIVE_STAGES + HAZARDOUS_STAGES
PHYSICAL_RESULT_VALUES = {
    "passed": QualificationStageStatus.PASSED,
    "failed": QualificationStageStatus.FAILED,
    "interrupted": QualificationStageStatus.INTERRUPTED,
}

DRIVE_NEUTRAL_PAYLOAD = {
    "vector": {"linear": 0.0, "angular": 0.0},
    "duration_ms": 0,
    "reason": "autonomy-qualification-cleanup",
    "max_speed_limit": 0.0,
}
BLADE_OFF_PAYLOAD = {"action": "disable", "reason": "autonomy-qualification-cleanup"}


class ApiClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def get(self, path: str) -> dict[str, Any]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        return self._request(req)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._request(req)

    def _request(self, req: urllib.request.Request) -> dict[str, Any]:
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            data = resp.read()
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stage(stage_id: str, status: QualificationStageStatus, summary: str, **extra: Any):
    return AutonomyQualificationStageResult(
        stage_id=stage_id,
        status=status,
        started_at=extra.pop("started_at", _now()),
        completed_at=extra.pop("completed_at", _now()),
        summary=summary,
        **extra,
    )


def _run_non_destructive_stage(client: ApiClient, stage_id: str) -> AutonomyQualificationStageResult:
    started_at = _now()
    if stage_id == "static_config":
        qualification = client.get("/api/v2/autonomy/qualification")
        context = qualification.get("context") or {}
        blockers = set(qualification.get("reason_codes") or [])
        context_blockers = {
            "QUALIFICATION_CONTEXT_INCOMPLETE",
            "QUALIFICATION_SIMULATION_MODE",
            "QUALIFICATION_GIT_TREE_DIRTY",
            "QUALIFICATION_FIRMWARE_UNKNOWN",
        }
        status = (
            QualificationStageStatus.FAILED
            if blockers.intersection(context_blockers)
            else QualificationStageStatus.PASSED
        )
        return _stage(
            stage_id,
            status,
            "Collected commit/config/limits/runtime/firmware qualification context.",
            started_at=started_at,
            measurements={
                "commit_sha": context.get("commit_sha"),
                "pi_model": context.get("pi_model"),
                "sim_mode": context.get("sim_mode"),
                "git_tree_dirty": context.get("git_tree_dirty"),
                "firmware_present": bool(context.get("robohat_firmware_version")),
            },
            reason_code=";".join(sorted(blockers.intersection(context_blockers))) or None,
        )
    if stage_id == "service_neutral":
        client.post("/api/v2/control/drive", DRIVE_NEUTRAL_PAYLOAD)
        client.post("/api/v2/control/blade", BLADE_OFF_PAYLOAD)
        robohat = client.get("/api/v2/hardware/robohat")
        return _stage(
            stage_id,
            QualificationStageStatus.PASSED,
            "Backend accepted cleanup neutral drive plus blade-off commands.",
            started_at=started_at,
            measurements={
                "serial_connected": bool(robohat.get("serial_connected")),
                "motor_controller_ok": bool(robohat.get("motor_controller_ok")),
            },
        )
    if stage_id == "sensor_freshness":
        health = client.get("/api/v2/sensors/health")
        unhealthy = []
        for name, payload in sorted((health or {}).items()):
            if isinstance(payload, dict) and payload.get("status") not in {None, "online", "ok"}:
                unhealthy.append(name)
        return _stage(
            stage_id,
            QualificationStageStatus.FAILED if unhealthy else QualificationStageStatus.PASSED,
            "Read sensor health through the backend owner API.",
            started_at=started_at,
            reason_code="SENSOR_HEALTH_BLOCKED" if unhealthy else None,
            measurements={"unhealthy": unhealthy},
        )
    return _stage(stage_id, QualificationStageStatus.SKIPPED, "Unknown non-destructive stage.")


def _cleanup(client: ApiClient) -> list[str]:
    errors: list[str] = []
    for path, payload in (
        ("/api/v2/control/drive", DRIVE_NEUTRAL_PAYLOAD),
        ("/api/v2/control/blade", BLADE_OFF_PAYLOAD),
    ):
        try:
            client.post(path, payload)
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    return errors


def _parse_stage_mapping(values: list[str] | None, option_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_value in values or []:
        stage_id, separator, value = raw_value.partition("=")
        if not separator or stage_id not in ALL_STAGES or not value:
            raise ValueError(f"{option_name} requires STAGE=VALUE for a known stage")
        parsed[stage_id] = value
    return parsed


def _parse_artifact_mapping(values: list[str] | None) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for raw_value in values or []:
        stage_id, separator, artifact_id = raw_value.partition("=")
        if not separator or stage_id not in ALL_STAGES or not artifact_id:
            raise ValueError("--artifact-id requires STAGE=ARTIFACT_ID for a known stage")
        parsed.setdefault(stage_id, []).append(artifact_id)
    return parsed


def _record_matches_context(record: dict[str, Any], context: dict[str, Any]) -> bool:
    binding_fields = (
        "commit_sha",
        "hardware_config_hash",
        "limits_hash",
        "runtime_identity_hash",
        "robohat_firmware_version",
        "sim_mode",
        "git_tree_dirty",
    )
    return all(record.get(field) == context.get(field) for field in binding_fields)


def _physical_stage_result(
    stage_id: str,
    *,
    stage_results: dict[str, str],
    artifacts: dict[str, list[str]],
    operator_confirmed: bool,
    physical_intervention: str,
    completed_stage_ids: set[str],
) -> AutonomyQualificationStageResult:
    started_at = _now()
    if not operator_confirmed:
        return _stage(
            stage_id,
            QualificationStageStatus.OPERATOR_REQUIRED,
            "Physical stage requires explicit operator confirmation before recording.",
            reason_code="OPERATOR_CONFIRMATION_REQUIRED",
            started_at=started_at,
        )
    result_value = stage_results.get(stage_id)
    if result_value is None:
        return _stage(
            stage_id,
            QualificationStageStatus.OPERATOR_REQUIRED,
            "Record the supervised physical result explicitly; this runner never infers a pass.",
            reason_code="MANUAL_PHYSICAL_EVIDENCE_REQUIRED",
            started_at=started_at,
        )
    if result_value not in PHYSICAL_RESULT_VALUES:
        return _stage(
            stage_id,
            QualificationStageStatus.FAILED,
            "Unsupported physical stage result.",
            reason_code="INVALID_STAGE_RESULT",
            started_at=started_at,
        )
    status = PHYSICAL_RESULT_VALUES[result_value]
    prerequisite_ids = set(ALL_STAGES[: ALL_STAGES.index(stage_id)])
    missing_prerequisites = sorted(prerequisite_ids - completed_stage_ids)
    if status == QualificationStageStatus.PASSED and missing_prerequisites:
        return _stage(
            stage_id,
            QualificationStageStatus.FAILED,
            "Physical stages must be retained in dependency order.",
            reason_code="STAGE_PREREQUISITE_MISSING",
            started_at=started_at,
            measurements={"missing_prerequisites": missing_prerequisites},
        )
    artifact_ids = artifacts.get(stage_id, [])
    if status == QualificationStageStatus.PASSED and (
        not physical_intervention.strip() or not artifact_ids
    ):
        return _stage(
            stage_id,
            QualificationStageStatus.FAILED,
            "Passing physical evidence requires the intervention mechanism and artifact IDs.",
            reason_code="PHYSICAL_EVIDENCE_INCOMPLETE",
            started_at=started_at,
        )
    return _stage(
        stage_id,
        status,
        "Recorded operator-confirmed physical qualification result without automatic actuation.",
        reason_code=None if status == QualificationStageStatus.PASSED else "PHYSICAL_STAGE_NOT_PASSED",
        started_at=started_at,
        artifact_ids=artifact_ids,
        measurements={
            "operator_confirmed": True,
            "physical_intervention_mechanism": physical_intervention.strip(),
        },
    )


def run(args: argparse.Namespace) -> AutonomyQualificationRecord:
    client = ApiClient(args.base_url, timeout_s=args.timeout_s)
    selected = tuple(args.stage or NON_DESTRUCTIVE_STAGES)
    if "all" in selected:
        selected = ALL_STAGES

    stage_results = _parse_stage_mapping(
        getattr(args, "stage_result", None),
        "--stage-result",
    )
    artifact_ids_by_stage = _parse_artifact_mapping(
        getattr(args, "artifact_id", None)
    )
    qualification = client.get("/api/v2/autonomy/qualification")
    initial_context = qualification["context"]
    stages_by_id: dict[str, AutonomyQualificationStageResult] = {}
    existing_record = qualification.get("record")
    if (
        not getattr(args, "fresh", False)
        and isinstance(existing_record, dict)
        and _record_matches_context(existing_record, initial_context)
    ):
        for stage_payload in existing_record.get("stages") or []:
            stage = AutonomyQualificationStageResult.model_validate(stage_payload)
            if stage.stage_id != "cleanup":
                stages_by_id[stage.stage_id] = stage

    cleanup_errors: list[str] = []
    try:
        for stage_id in selected:
            if stage_id not in ALL_STAGES:
                stages_by_id[stage_id] = _stage(
                    stage_id,
                    QualificationStageStatus.FAILED,
                    f"Unknown stage {stage_id}",
                    reason_code="UNKNOWN_STAGE",
                )
                continue
            if stage_id in HAZARDOUS_STAGES:
                completed_stage_ids = {
                    existing_stage_id
                    for existing_stage_id, existing_stage in stages_by_id.items()
                    if existing_stage.status == QualificationStageStatus.PASSED
                }
                stages_by_id[stage_id] = _physical_stage_result(
                    stage_id,
                    stage_results=stage_results,
                    artifacts=artifact_ids_by_stage,
                    operator_confirmed=args.operator_confirmed,
                    physical_intervention=getattr(args, "physical_intervention", ""),
                    completed_stage_ids=completed_stage_ids,
                )
                continue
            try:
                stages_by_id[stage_id] = _run_non_destructive_stage(client, stage_id)
            except Exception as exc:
                stages_by_id[stage_id] = _stage(
                    stage_id,
                    QualificationStageStatus.FAILED,
                    f"Stage failed: {exc}",
                    reason_code="STAGE_API_ERROR",
                )
    finally:
        cleanup_errors = _cleanup(client)

    if cleanup_errors:
        stages_by_id["cleanup"] = _stage(
            "cleanup",
            QualificationStageStatus.FAILED,
            "Cleanup commands did not all confirm.",
            reason_code="CLEANUP_FAILED",
            measurements={"errors": cleanup_errors},
        )
    else:
        stages_by_id["cleanup"] = _stage(
            "cleanup",
            QualificationStageStatus.PASSED,
            "Cleanup commanded drive neutral and blade off.",
        )

    ordered_stage_ids = (*ALL_STAGES, "cleanup")
    stages = [stages_by_id[stage_id] for stage_id in ordered_stage_ids if stage_id in stages_by_id]
    stages.extend(
        stage
        for stage_id, stage in stages_by_id.items()
        if stage_id not in ordered_stage_ids
    )
    required_stages_passed = all(
        stages_by_id.get(stage_id) is not None
        and stages_by_id[stage_id].status == QualificationStageStatus.PASSED
        for stage_id in BLADE_ENABLED_REQUIRED_STAGES
    )
    if required_stages_passed:
        overall = QualificationStageStatus.PASSED
    elif any(stage.status == QualificationStageStatus.FAILED for stage in stages):
        overall = QualificationStageStatus.FAILED
    else:
        overall = QualificationStageStatus.INTERRUPTED

    qualification = client.get("/api/v2/autonomy/qualification")
    context = qualification["context"]
    record = AutonomyQualificationRecord(
        status=overall,
        commit_sha=context.get("commit_sha"),
        git_tree_dirty=bool(context.get("git_tree_dirty")),
        hardware_config_hash=context.get("hardware_config_hash"),
        limits_hash=context.get("limits_hash"),
        runtime_identity_hash=context["runtime_identity_hash"],
        pi_model=context.get("pi_model", "unknown"),
        hostname_hash=context["hostname_hash"],
        machine_id_hash=context.get("machine_id_hash"),
        os_release=context.get("os_release", "unknown"),
        sim_mode=bool(context.get("sim_mode")),
        robohat_firmware_version=context.get("robohat_firmware_version"),
        stages=stages,
        artifact_ids=list(
            dict.fromkeys(
                artifact_id
                for stage in stages
                for artifact_id in stage.artifact_ids
            )
        ),
        operator_id=args.operator,
        notes=args.notes or "",
    )

    if args.store:
        client.post("/api/v2/autonomy/qualification/evidence", record.model_dump(mode="json"))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run staged LawnBerry autonomy qualification.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8081")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--stage", action="append", choices=("all", *ALL_STAGES))
    parser.add_argument("--operator-confirmed", action="store_true")
    parser.add_argument(
        "--stage-result",
        action="append",
        metavar="STAGE=passed|failed|interrupted",
        help="Record an explicitly supervised physical stage result; never actuates hardware.",
    )
    parser.add_argument(
        "--artifact-id",
        action="append",
        metavar="STAGE=ARTIFACT_ID",
        help="Attach a retained verification-artifact registry ID to a physical stage.",
    )
    parser.add_argument(
        "--physical-intervention",
        default="",
        help="Configured independent hazardous-power cutoff used during supervised tests.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Do not carry forward same-context stage evidence from the latest record.",
    )
    parser.add_argument("--operator", default="operator")
    parser.add_argument("--notes", default="")
    parser.add_argument("--store", action="store_true")
    parser.add_argument("--output", default="-")
    args = parser.parse_args()

    try:
        record = run(args)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"qualification runner failed before record creation: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True)
    if args.output == "-":
        print(payload)
    else:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
    return 0 if record.status == QualificationStageStatus.PASSED else 1


if __name__ == "__main__":
    raise SystemExit(main())
