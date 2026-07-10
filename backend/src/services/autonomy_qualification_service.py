from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from ..hardware.platform_profile import detect_platform_profile
from ..models.autonomy_qualification import (
    QUALIFICATION_SCHEMA_VERSION,
    AutonomyQualificationContext,
    AutonomyQualificationEvaluation,
    AutonomyQualificationRecord,
    QualificationStageStatus,
)

BLADE_ENABLED_REQUIRED_STAGES: tuple[str, ...] = (
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

BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES: tuple[str, ...] = (
    "static_config",
    "service_neutral",
    "sensor_freshness",
)

PHYSICAL_EVIDENCE_STAGES: frozenset[str] = frozenset(
    {
        "wheels_raised_drive",
        "failsafe_shutdown",
        "stationary_rtk_geofence",
        "blade_off_motion",
        "straight_line_cross_track",
        "obstacle_stop",
        "mission_scheduler_recovery",
        "webui_network_recovery",
    }
)

SECRET_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private",
    "ntrip",
    "cloudflare",
    "google",
)

REMEDIATION: dict[str, str] = {
    "QUALIFICATION_EVIDENCE_MISSING": "Run the on-device autonomy qualification workflow and store passing evidence.",
    "QUALIFICATION_EVIDENCE_STALE": "Re-run qualification because the retained evidence is older than the allowed window.",
    "QUALIFICATION_EVIDENCE_FAILED": "Repeat the failed qualification stage after correcting the recorded blocker.",
    "QUALIFICATION_EVIDENCE_INTERRUPTED": "Repeat qualification; interrupted runs cannot authorize hazardous operation.",
    "QUALIFICATION_SCHEMA_MISMATCH": "Re-run qualification with the current software schema.",
    "QUALIFICATION_COMMIT_MISMATCH": "Re-run qualification on the currently deployed commit.",
    "QUALIFICATION_GIT_TREE_DIRTY": "Deploy a clean committed revision before recording or using physical qualification evidence.",
    "QUALIFICATION_HARDWARE_CONFIG_MISMATCH": "Re-run qualification after hardware configuration changes.",
    "QUALIFICATION_LIMITS_MISMATCH": "Re-run qualification after safety-limit changes.",
    "QUALIFICATION_RUNTIME_IDENTITY_MISMATCH": "Re-run qualification on this Raspberry Pi/runtime identity.",
    "QUALIFICATION_FIRMWARE_UNKNOWN": "Confirm RoboHAT firmware version and re-run qualification.",
    "QUALIFICATION_FIRMWARE_MISMATCH": "Re-run qualification after RoboHAT firmware changes.",
    "QUALIFICATION_STAGE_MISSING": "Complete every required qualification stage before enabling blade-capable autonomy.",
    "QUALIFICATION_STAGE_FAILED": "Correct the failed stage and re-run qualification.",
    "QUALIFICATION_STAGE_INTERRUPTED": "Repeat the interrupted qualification stage.",
    "QUALIFICATION_STAGE_ARTIFACT_MISSING": "Attach retained evidence to every required physical qualification stage.",
    "QUALIFICATION_STAGE_ARTIFACT_INVALID": "Recreate stage evidence with current context bindings and operator confirmation.",
    "QUALIFICATION_RECORD_INVALID": "Regenerate the qualification record; stage identifiers and artifact references must be consistent.",
    "QUALIFICATION_RECORD_EXISTS": "Create a new immutable qualification record ID instead of replacing retained evidence.",
    "QUALIFICATION_SIMULATION_MODE": "Physical qualification must run with SIM_MODE=0 on the mower.",
    "QUALIFICATION_CONTEXT_INCOMPLETE": "Resolve missing commit, config, limits, runtime, or firmware identity before qualification.",
    "QUALIFICATION_SERVICE_UNAVAILABLE": "Restart the backend and verify the qualification service is wired.",
}


class AutonomyQualificationError(RuntimeError):
    def __init__(self, evaluation: AutonomyQualificationEvaluation):
        super().__init__(", ".join(evaluation.reason_codes) or "QUALIFICATION_NOT_READY")
        self.evaluation = evaluation


class AutonomyQualificationService:
    def __init__(
        self,
        runtime: Any,
        *,
        root_dir: Path | None = None,
        ttl_days: int = 30,
    ) -> None:
        self._runtime = runtime
        self._root_dir = root_dir or Path(__file__).resolve().parents[3]
        self._ttl = timedelta(days=ttl_days)
        self._records_dir = (
            self._root_dir / "verification_artifacts" / "autonomy-qualification"
        )
        self._latest_path = self._records_dir / "latest.json"
        self._artifact_registry_dir = self._root_dir / "verification_artifacts" / "registry"

    @property
    def records_dir(self) -> Path:
        return self._records_dir

    def build_context(self) -> AutonomyQualificationContext:
        platform_profile = detect_platform_profile()
        hostname = socket.gethostname() or "unknown"
        hostname_hash = _sha256_text(hostname)
        machine_id_hash = _read_machine_id_hash()
        hardware_hash = self._hardware_config_hash()
        limits_hash = self._limits_hash()
        firmware = self._robohat_firmware_version()
        os_release = _read_os_release()
        runtime_identity_hash = _sha256_json(
            {
                "pi_model": platform_profile.model,
                "hostname_hash": hostname_hash,
                "machine_id_hash": machine_id_hash,
                "os_release": os_release,
            }
        )
        return AutonomyQualificationContext(
            commit_sha=_git_output(self._root_dir, "rev-parse", "HEAD"),
            git_tree_dirty=_git_tree_dirty(self._root_dir),
            hardware_config_hash=hardware_hash,
            limits_hash=limits_hash,
            runtime_identity_hash=runtime_identity_hash,
            pi_model=platform_profile.model,
            hostname_hash=hostname_hash,
            machine_id_hash=machine_id_hash,
            os_release=os_release,
            sim_mode=os.getenv("SIM_MODE", "0") == "1",
            robohat_firmware_version=firmware,
        )

    def build_record_from_current_context(
        self,
        *,
        status: QualificationStageStatus,
        stages: list[Any],
        artifact_ids: list[str] | None = None,
        operator_id: str | None = None,
        notes: str = "",
    ) -> AutonomyQualificationRecord:
        context = self.build_context()
        return AutonomyQualificationRecord(
            status=status,
            commit_sha=context.commit_sha,
            git_tree_dirty=context.git_tree_dirty,
            hardware_config_hash=context.hardware_config_hash,
            limits_hash=context.limits_hash,
            runtime_identity_hash=context.runtime_identity_hash,
            pi_model=context.pi_model,
            hostname_hash=context.hostname_hash,
            machine_id_hash=context.machine_id_hash,
            os_release=context.os_release,
            sim_mode=context.sim_mode,
            robohat_firmware_version=context.robohat_firmware_version,
            stages=stages,
            artifact_ids=artifact_ids or [],
            operator_id=operator_id,
            notes=notes,
        )

    def save_record(self, record: AutonomyQualificationRecord) -> None:
        context = self.build_context()
        if record.status == QualificationStageStatus.PASSED:
            reasons = self._record_reason_codes(
                record,
                context,
                BLADE_ENABLED_REQUIRED_STAGES,
            )
            if reasons:
                raise AutonomyQualificationError(
                    _evaluation(
                        context,
                        record,
                        BLADE_ENABLED_REQUIRED_STAGES,
                        reasons,
                    )
                )
        self._records_dir.mkdir(parents=True, exist_ok=True)
        record_path = self._records_dir / f"{record.record_id}.json"
        if record_path.exists():
            raise AutonomyQualificationError(
                _evaluation(
                    context,
                    record,
                    BLADE_ENABLED_REQUIRED_STAGES,
                    ["QUALIFICATION_RECORD_EXISTS"],
                )
            )
        payload = record.model_dump(mode="json")
        _write_json_atomic(record_path, payload)
        _write_json_atomic(self._latest_path, payload)

    def load_latest_record(self) -> AutonomyQualificationRecord | None:
        try:
            return AutonomyQualificationRecord.model_validate_json(
                self._latest_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def evaluate(
        self,
        *,
        required_stage_ids: tuple[str, ...] = BLADE_ENABLED_REQUIRED_STAGES,
    ) -> AutonomyQualificationEvaluation:
        context = self.build_context()
        record = self.load_latest_record()
        reasons: list[str] = []

        if context.sim_mode:
            reasons.append("QUALIFICATION_SIMULATION_MODE")
        if context.git_tree_dirty:
            reasons.append("QUALIFICATION_GIT_TREE_DIRTY")
        if (
            context.commit_sha is None
            or context.hardware_config_hash is None
            or context.limits_hash is None
            or context.runtime_identity_hash is None
        ):
            reasons.append("QUALIFICATION_CONTEXT_INCOMPLETE")
        if context.robohat_firmware_version is None:
            reasons.append("QUALIFICATION_FIRMWARE_UNKNOWN")

        if record is None:
            reasons.append("QUALIFICATION_EVIDENCE_MISSING")
            return _evaluation(context, record, required_stage_ids, reasons)

        reasons.extend(self._record_reason_codes(record, context, required_stage_ids))

        return _evaluation(context, record, required_stage_ids, reasons)

    def assert_current(
        self,
        *,
        required_stage_ids: tuple[str, ...] = BLADE_ENABLED_REQUIRED_STAGES,
    ) -> AutonomyQualificationEvaluation:
        evaluation = self.evaluate(required_stage_ids=required_stage_ids)
        if not evaluation.ok:
            raise AutonomyQualificationError(evaluation)
        return evaluation

    def _record_reason_codes(
        self,
        record: AutonomyQualificationRecord,
        context: AutonomyQualificationContext,
        required_stage_ids: tuple[str, ...],
    ) -> list[str]:
        reasons: list[str] = []
        if record.schema_version != QUALIFICATION_SCHEMA_VERSION:
            reasons.append("QUALIFICATION_SCHEMA_MISMATCH")
        if record.status == QualificationStageStatus.FAILED:
            reasons.append("QUALIFICATION_EVIDENCE_FAILED")
        elif record.status == QualificationStageStatus.INTERRUPTED:
            reasons.append("QUALIFICATION_EVIDENCE_INTERRUPTED")
        elif record.status != QualificationStageStatus.PASSED:
            reasons.append("QUALIFICATION_EVIDENCE_FAILED")

        created_at = _parse_iso(record.created_at)
        if created_at is None or datetime.now(UTC) - created_at > self._ttl:
            reasons.append("QUALIFICATION_EVIDENCE_STALE")

        if context.sim_mode or record.sim_mode:
            reasons.append("QUALIFICATION_SIMULATION_MODE")
        if context.git_tree_dirty or record.git_tree_dirty:
            reasons.append("QUALIFICATION_GIT_TREE_DIRTY")
        _append_if_mismatch(
            reasons,
            record.commit_sha,
            context.commit_sha,
            "QUALIFICATION_COMMIT_MISMATCH",
        )
        _append_if_mismatch(
            reasons,
            record.hardware_config_hash,
            context.hardware_config_hash,
            "QUALIFICATION_HARDWARE_CONFIG_MISMATCH",
        )
        _append_if_mismatch(
            reasons,
            record.limits_hash,
            context.limits_hash,
            "QUALIFICATION_LIMITS_MISMATCH",
        )
        _append_if_mismatch(
            reasons,
            record.runtime_identity_hash,
            context.runtime_identity_hash,
            "QUALIFICATION_RUNTIME_IDENTITY_MISMATCH",
        )
        _append_if_mismatch(
            reasons,
            record.robohat_firmware_version,
            context.robohat_firmware_version,
            "QUALIFICATION_FIRMWARE_MISMATCH",
        )

        stage_ids = [stage.stage_id for stage in record.stages]
        if len(stage_ids) != len(set(stage_ids)):
            reasons.append("QUALIFICATION_RECORD_INVALID")
        stages = {stage.stage_id: stage for stage in record.stages}
        record_artifact_ids = set(record.artifact_ids)
        for stage_id in required_stage_ids:
            stage = stages.get(stage_id)
            if stage is None:
                reasons.append("QUALIFICATION_STAGE_MISSING")
                continue
            if stage.status == QualificationStageStatus.FAILED:
                reasons.append("QUALIFICATION_STAGE_FAILED")
            elif stage.status == QualificationStageStatus.INTERRUPTED:
                reasons.append("QUALIFICATION_STAGE_INTERRUPTED")
            elif stage.status != QualificationStageStatus.PASSED:
                reasons.append("QUALIFICATION_STAGE_MISSING")
            if stage_id not in PHYSICAL_EVIDENCE_STAGES:
                continue
            if not stage.artifact_ids:
                reasons.append("QUALIFICATION_STAGE_ARTIFACT_MISSING")
                continue
            if not set(stage.artifact_ids).issubset(record_artifact_ids):
                reasons.append("QUALIFICATION_RECORD_INVALID")
            if not all(
                self._artifact_matches_context(artifact_id, stage_id, context)
                for artifact_id in stage.artifact_ids
            ):
                reasons.append("QUALIFICATION_STAGE_ARTIFACT_INVALID")
        return reasons

    def _artifact_matches_context(
        self,
        artifact_id: str,
        stage_id: str,
        context: AutonomyQualificationContext,
    ) -> bool:
        try:
            payload = json.loads(
                (self._artifact_registry_dir / f"{artifact_id}.json").read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            return False
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            return False
        expected = {
            "qualification_stage_id": stage_id,
            "commit_sha": context.commit_sha,
            "hardware_config_hash": context.hardware_config_hash,
            "limits_hash": context.limits_hash,
            "runtime_identity_hash": context.runtime_identity_hash,
            "robohat_firmware_version": context.robohat_firmware_version,
            "result": "passed",
            "operator_confirmed": True,
        }
        return payload.get("artifact_id") == artifact_id and all(
            metadata.get(key) == value for key, value in expected.items()
        )

    def _hardware_config_hash(self) -> str | None:
        loader = getattr(self._runtime, "config_loader", None)
        path = Path(getattr(loader, "hardware_path", "")) if loader is not None else None
        if path and str(path) and path.exists():
            return _hash_yaml_file(path)
        hardware = getattr(self._runtime, "hardware_config", None)
        if hardware is not None and callable(getattr(hardware, "model_dump", None)):
            return _sha256_json(_redact(hardware.model_dump(mode="json")))
        return None

    def _limits_hash(self) -> str | None:
        limits = getattr(self._runtime, "safety_limits", None)
        if limits is not None and callable(getattr(limits, "model_dump", None)):
            return _sha256_json(_redact(limits.model_dump(mode="json")))
        loader = getattr(self._runtime, "config_loader", None)
        path = Path(getattr(loader, "limits_path", "")) if loader is not None else None
        if path and str(path) and path.exists():
            return _hash_yaml_file(path)
        return None

    def _robohat_firmware_version(self) -> str | None:
        robohat = getattr(self._runtime, "robohat", None)
        status = getattr(robohat, "status", None)
        value = getattr(status, "firmware_version", None)
        return str(value) if value else None


def _evaluation(
    context: AutonomyQualificationContext,
    record: AutonomyQualificationRecord | None,
    required_stage_ids: tuple[str, ...],
    reasons: list[str],
) -> AutonomyQualificationEvaluation:
    unique_reasons = list(dict.fromkeys(reasons))
    return AutonomyQualificationEvaluation(
        ok=not unique_reasons,
        reason_codes=unique_reasons,
        remediation=_remediation(unique_reasons),
        required_stage_ids=list(required_stage_ids),
        context=context,
        record=record,
    )


def _remediation(reason_codes: list[str]) -> dict[str, str]:
    return {code: REMEDIATION.get(code, "Review autonomy qualification evidence.") for code in reason_codes}


def _append_if_mismatch(reasons: list[str], left: Any, right: Any, code: str) -> None:
    if left != right:
        reasons.append(code)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _hash_yaml_file(path: Path) -> str | None:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return _sha256_json(_redact(payload))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            key_text = str(key).lower()
            if any(part in key_text for part in SECRET_KEY_PARTS):
                redacted[str(key)] = "<redacted>"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_text(payload)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _git_output(root_dir: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", *args),
            cwd=root_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _git_tree_dirty(root_dir: Path) -> bool:
    try:
        result = subprocess.run(
            ("git", "status", "--porcelain"),
            cwd=root_dir,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except Exception:
        return True


def _read_machine_id_hash() -> str | None:
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return _sha256_text(value)
        except Exception:
            continue
    return None


def _read_os_release() -> str:
    try:
        data = Path("/etc/os-release").read_text(encoding="utf-8")
    except Exception:
        return platform.platform()
    fields: dict[str, str] = {}
    for line in data.splitlines():
        if "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        fields[key] = raw_value.strip().strip('"')
    return fields.get("PRETTY_NAME") or platform.platform()
