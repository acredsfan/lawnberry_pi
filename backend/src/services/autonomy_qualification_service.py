from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import re
import secrets
import socket
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from ..hardware.platform_profile import detect_platform_profile
from ..models.autonomy_qualification import (
    QUALIFICATION_SCHEMA_VERSION,
    AutonomyQualificationContext,
    AutonomyQualificationEvaluation,
    AutonomyQualificationRecord,
    QualificationLevel,
    QualificationStageStatus,
    SupervisedTestPermitIssueResponse,
    SupervisedTestPermitState,
    SupervisedTestPermitStatus,
)

logger = logging.getLogger(__name__)

BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES: tuple[str, ...] = (
    "static_config",
    "service_neutral",
    "sensor_freshness",
)

SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES: tuple[str, ...] = (
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

FULL_BLADE_AUTONOMY_REQUIRED_STAGES: tuple[str, ...] = (
    *SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES,
    "supervised_blade_enabled",
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
        "supervised_blade_enabled",
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
    "QUALIFICATION_EVIDENCE_MISSING": (
        "Run the on-device autonomy qualification workflow and store passing evidence."
    ),
    "QUALIFICATION_EVIDENCE_STALE": (
        "Re-run qualification because retained evidence is older than the allowed window."
    ),
    "QUALIFICATION_EVIDENCE_FAILED": (
        "Repeat the failed qualification stage after correcting the recorded blocker."
    ),
    "QUALIFICATION_EVIDENCE_INTERRUPTED": (
        "Repeat qualification; interrupted runs cannot authorize hazardous operation."
    ),
    "QUALIFICATION_SCHEMA_MISMATCH": (
        "Schema-v1 evidence is historical only; re-run the schema-v2 qualification workflow."
    ),
    "QUALIFICATION_LEVEL_MISMATCH": (
        "Store evidence at the requested typed qualification level."
    ),
    "QUALIFICATION_COMMIT_MISMATCH": "Re-run qualification on the deployed commit.",
    "QUALIFICATION_GIT_TREE_DIRTY": (
        "Deploy a clean committed revision before recording or using physical evidence."
    ),
    "QUALIFICATION_HARDWARE_CONFIG_MISMATCH": (
        "Re-run qualification after hardware configuration changes."
    ),
    "QUALIFICATION_LIMITS_MISMATCH": (
        "Re-run qualification after safety-limit changes."
    ),
    "QUALIFICATION_RUNTIME_IDENTITY_MISMATCH": (
        "Re-run qualification on this Raspberry Pi/runtime identity."
    ),
    "QUALIFICATION_FIRMWARE_UNKNOWN": (
        "Confirm RoboHAT firmware version and re-run qualification."
    ),
    "QUALIFICATION_FIRMWARE_MISMATCH": (
        "Re-run qualification after RoboHAT firmware changes."
    ),
    "QUALIFICATION_STAGE_MISSING": "Complete every required qualification stage.",
    "QUALIFICATION_STAGE_FAILED": "Correct the failed stage and re-run qualification.",
    "QUALIFICATION_STAGE_INTERRUPTED": "Repeat the interrupted qualification stage.",
    "QUALIFICATION_STAGE_ARTIFACT_MISSING": (
        "Attach retained evidence to every required physical qualification stage."
    ),
    "QUALIFICATION_STAGE_ARTIFACT_INVALID": (
        "Recreate stage evidence with current context bindings and operator confirmation."
    ),
    "QUALIFICATION_RECORD_INVALID": (
        "Regenerate the record; stage identifiers and artifact references must be consistent."
    ),
    "QUALIFICATION_RECORD_EXISTS": (
        "Create a new immutable qualification record instead of replacing retained evidence."
    ),
    "QUALIFICATION_SIMULATION_MODE": (
        "Physical qualification must run with SIM_MODE=0 on the mower."
    ),
    "QUALIFICATION_CONTEXT_INCOMPLETE": (
        "Resolve missing commit, config, limits, runtime, or firmware identity."
    ),
    "QUALIFICATION_SERVICE_UNAVAILABLE": (
        "Restart the backend and verify the qualification service is wired."
    ),
    "SUPERVISED_BLADE_TEST_REQUIRED": (
        "Complete and retain the supervised_blade_enabled artifact before full autonomy."
    ),
    "SUPERVISED_TEST_RECEIPT_INVALID": (
        "Use the server cleanup receipt from the same completed supervised-test permit."
    ),
    "SUPERVISED_TEST_DISABLED": (
        "Keep the mower blade off until Aaron approves and configures physical test bounds."
    ),
    "SUPERVISED_TEST_FULL_QUALIFICATION_CURRENT": (
        "A supervised-test permit is unnecessary while full qualification is current; "
        "record a new prerequisite run first if requalification is required."
    ),
    "SUPERVISED_TEST_OPERATOR_CONFIRMATION_REQUIRED": (
        "The authenticated local operator must explicitly confirm supervision and cutoff access."
    ),
    "SUPERVISED_TEST_PERMIT_EXPIRED": (
        "Confirm neutral and blade off, then request a new permit after operator review."
    ),
    "SUPERVISED_TEST_PERMIT_CONTEXT_MISMATCH": (
        "Confirm neutral and blade off, then repeat prerequisite qualification in this context."
    ),
}

_LEVEL_STAGES: dict[QualificationLevel, tuple[str, ...]] = {
    QualificationLevel.BLADE_OFF_DIAGNOSTIC: BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES,
    QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE: (
        SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES
    ),
    QualificationLevel.FULL_BLADE_AUTONOMY: FULL_BLADE_AUTONOMY_REQUIRED_STAGES,
}
_LEVEL_RANK: dict[QualificationLevel, int] = {
    QualificationLevel.BLADE_OFF_DIAGNOSTIC: 0,
    QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE: 1,
    QualificationLevel.FULL_BLADE_AUTONOMY: 2,
}
_NONTERMINAL_PERMIT_STATES = {
    SupervisedTestPermitState.ISSUED,
    SupervisedTestPermitState.ACTIVE,
}
_EVIDENCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AutonomyQualificationError(RuntimeError):
    def __init__(self, evaluation: AutonomyQualificationEvaluation):
        super().__init__(", ".join(evaluation.reason_codes) or "QUALIFICATION_NOT_READY")
        self.evaluation = evaluation


class SupervisedTestPermitError(RuntimeError):
    def __init__(self, reason_code: str, status: SupervisedTestPermitStatus):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.status = status


@dataclass
class _Permit:
    token_digest: str
    permit_id_hash: str
    operator_id: str
    operator_session_hash: str
    qualification_record_id: str
    context_binding: dict[str, Any]
    physical_intervention_mechanism: str
    state: SupervisedTestPermitState
    issued_at: datetime
    activated_at: datetime | None
    expires_at: datetime
    expires_monotonic: float
    max_speed_mps: float
    max_duration_seconds: float
    terminal_reason_code: str | None = None
    receipt_id: str | None = None
    receipt_evidence_eligible: bool = False
    drive_command_count: int = 0
    blade_enable_command_count: int = 0


class AutonomyQualificationService:
    def __init__(
        self,
        runtime: Any,
        *,
        root_dir: Path | None = None,
        ttl_days: int = 30,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runtime = runtime
        self._root_dir = root_dir or Path(__file__).resolve().parents[3]
        self._ttl = timedelta(days=ttl_days)
        self._records_dir = self._root_dir / "verification_artifacts" / "autonomy-qualification"
        self._latest_path = self._records_dir / "latest.json"
        self._receipts_dir = self._records_dir / "receipts"
        self._receipt_claims_dir = self._records_dir / "receipt-claims"
        self._artifact_registry_dir = self._root_dir / "verification_artifacts" / "registry"
        self._monotonic = monotonic
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._permit_lock = threading.RLock()
        self._record_lock = threading.RLock()
        # Deliberately memory-only: a backend restart always starts with no capability.
        self._permit: _Permit | None = None

    @property
    def records_dir(self) -> Path:
        return self._records_dir

    @property
    def receipts_dir(self) -> Path:
        return self._receipts_dir

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
            generated_at=self._wall_clock().isoformat(),
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
        qualification_level: QualificationLevel = QualificationLevel.FULL_BLADE_AUTONOMY,
        artifact_ids: list[str] | None = None,
        operator_id: str | None = None,
        notes: str = "",
    ) -> AutonomyQualificationRecord:
        context = self.build_context()
        return AutonomyQualificationRecord(
            created_at=self._wall_clock().isoformat(),
            qualification_level=qualification_level,
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
        with self._record_lock:
            context = self.build_context()
            level = QualificationLevel(record.qualification_level)
            required_stages = _LEVEL_STAGES[level]
            if record.status == QualificationStageStatus.PASSED:
                reasons = self._record_reason_codes(record, context, required_stages, level)
                if reasons:
                    raise AutonomyQualificationError(
                        self._evaluation_for(
                            context,
                            record,
                            requested_level=level,
                            required_stage_ids=required_stages,
                            reasons=reasons,
                        )
                    )
            self._records_dir.mkdir(parents=True, exist_ok=True)
            record_path = self._records_dir / f"{record.record_id}.json"
            if record_path.exists():
                raise AutonomyQualificationError(
                    self._evaluation_for(
                        context,
                        record,
                        requested_level=level,
                        required_stage_ids=required_stages,
                        reasons=["QUALIFICATION_RECORD_EXISTS"],
                    )
                )
            if (
                record.status == QualificationStageStatus.PASSED
                and level == QualificationLevel.FULL_BLADE_AUTONOMY
                and not self._claim_supervised_receipts(record)
            ):
                raise AutonomyQualificationError(
                    self._evaluation_for(
                        context,
                        record,
                        requested_level=level,
                        required_stage_ids=required_stages,
                        reasons=["SUPERVISED_TEST_RECEIPT_INVALID"],
                    )
                )
            payload = record.model_dump(mode="json")
            _write_json_atomic(record_path, payload)
            _write_json_atomic(self._latest_path, payload)
        self._audit(
            "qualification.evidence.saved",
            record_id=record.record_id,
            qualification_level=level.value,
            schema_version=record.schema_version,
        )

    def load_latest_record(self) -> AutonomyQualificationRecord | None:
        try:
            return AutonomyQualificationRecord.model_validate_json(
                self._latest_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ValueError, TypeError):
            return None

    def evaluate(
        self,
        *,
        required_stage_ids: tuple[str, ...] | None = None,
        required_level: QualificationLevel = QualificationLevel.FULL_BLADE_AUTONOMY,
    ) -> AutonomyQualificationEvaluation:
        if required_stage_ids is not None:
            required_level = _level_for_stages(required_stage_ids, required_level)
        else:
            required_stage_ids = _LEVEL_STAGES[required_level]

        context = self.build_context()
        record = self.load_latest_record()
        prerequisite_reasons = self._evaluation_reasons(
            context,
            record,
            SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES,
            QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE,
        )
        full_reasons = self._evaluation_reasons(
            context,
            record,
            FULL_BLADE_AUTONOMY_REQUIRED_STAGES,
            QualificationLevel.FULL_BLADE_AUTONOMY,
        )
        requested_reasons = self._evaluation_reasons(
            context,
            record,
            required_stage_ids,
            required_level,
        )
        return self._evaluation_for(
            context,
            record,
            requested_level=required_level,
            required_stage_ids=required_stage_ids,
            reasons=requested_reasons,
            prerequisite_reasons=prerequisite_reasons,
            full_reasons=full_reasons,
        )

    def assert_current(
        self,
        required_stage_ids: tuple[str, ...] | None = None,
        *,
        required_level: QualificationLevel = QualificationLevel.FULL_BLADE_AUTONOMY,
    ) -> AutonomyQualificationEvaluation:
        evaluation = self.evaluate(
            required_stage_ids=required_stage_ids,
            required_level=required_level,
        )
        if not evaluation.ok:
            raise AutonomyQualificationError(evaluation)
        return evaluation

    def assert_prerequisite_current(self) -> AutonomyQualificationEvaluation:
        return self.assert_current(
            SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES,
            required_level=QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE,
        )

    def issue_supervised_test_permit(
        self,
        *,
        operator_id: str,
        operator_session_id: str,
        operator_confirmed: bool,
        local_supervision_confirmed: bool,
        physical_intervention_mechanism: str,
    ) -> SupervisedTestPermitIssueResponse:
        with self._permit_lock:
            self._expire_locked()
            if self._permit and self._permit.state in _NONTERMINAL_PERMIT_STATES:
                self._raise_permit("SUPERVISED_TEST_PERMIT_ALREADY_EXISTS")
            limits = self._runtime.safety_limits
            if not bool(getattr(limits, "supervised_test_enabled", False)):
                self._raise_permit("SUPERVISED_TEST_DISABLED")
            permit_ttl = int(getattr(limits, "supervised_test_permit_ttl_s", 0))
            max_duration = float(getattr(limits, "supervised_test_max_duration_s", 0))
            max_speed = float(getattr(limits, "supervised_test_max_speed_mps", 0))
            if permit_ttl <= 0 or max_duration <= 0 or max_speed <= 0:
                self._raise_permit("SUPERVISED_TEST_LIMITS_INVALID")
            if (
                not operator_confirmed
                or not local_supervision_confirmed
                or len(physical_intervention_mechanism.strip()) < 8
            ):
                self._raise_permit("SUPERVISED_TEST_OPERATOR_CONFIRMATION_REQUIRED")

            evaluation = self.assert_prerequisite_current()
            if evaluation.record is None:
                self._raise_permit("SUPERVISED_TEST_PREREQUISITE_INVALID")
            if evaluation.full_autonomy_ok:
                self._raise_permit("SUPERVISED_TEST_FULL_QUALIFICATION_CURRENT")
            context = evaluation.context
            if context.sim_mode:
                self._raise_permit("SUPERVISED_TEST_HARDWARE_MODE_REQUIRED")

            now_mono = self._monotonic()
            now_wall = self._wall_clock()
            token = secrets.token_urlsafe(32)
            permit_identity = str(uuid4())
            self._permit = _Permit(
                token_digest=_sha256_text(token),
                permit_id_hash=_sha256_text(permit_identity)[:16],
                operator_id=operator_id,
                operator_session_hash=_sha256_text(operator_session_id),
                qualification_record_id=evaluation.record.record_id,
                context_binding=_context_binding(context),
                physical_intervention_mechanism=physical_intervention_mechanism.strip(),
                state=SupervisedTestPermitState.ISSUED,
                issued_at=now_wall,
                activated_at=None,
                expires_at=now_wall + timedelta(seconds=permit_ttl),
                expires_monotonic=now_mono + permit_ttl,
                max_speed_mps=max_speed,
                max_duration_seconds=max_duration,
            )
            self._audit_permit("issued")
            return SupervisedTestPermitIssueResponse(
                permit_token=token,
                status=self._permit_status_locked(),
            )

    def activate_supervised_test_permit(
        self,
        *,
        permit_token: str,
        operator_session_id: str,
    ) -> SupervisedTestPermitStatus:
        with self._permit_lock:
            self._require_permit_locked(
                permit_token,
                operator_session_id,
                expected_state=SupervisedTestPermitState.ISSUED,
            )
            assert self._permit is not None
            now_wall = self._wall_clock()
            self._permit.state = SupervisedTestPermitState.ACTIVE
            self._permit.activated_at = now_wall
            self._permit.expires_at = now_wall + timedelta(
                seconds=self._permit.max_duration_seconds
            )
            self._permit.expires_monotonic = (
                self._monotonic() + self._permit.max_duration_seconds
            )
            self._audit_permit("activated")
            return self._permit_status_locked()

    def authorize_supervised_command(
        self,
        *,
        permit_token: str,
        operator_session_id: str,
        command_type: str,
        left_normalized: float | None = None,
        right_normalized: float | None = None,
        duration_ms: int | None = None,
    ) -> SupervisedTestPermitStatus:
        with self._permit_lock:
            self._require_permit_locked(
                permit_token,
                operator_session_id,
                expected_state=SupervisedTestPermitState.ACTIVE,
            )
            assert self._permit is not None
            if command_type not in {"drive", "blade", "cleanup"}:
                self._raise_permit("SUPERVISED_TEST_COMMAND_SOURCE_INVALID")
            if command_type == "drive":
                if left_normalized is None or right_normalized is None or duration_ms is None:
                    self._raise_permit("SUPERVISED_TEST_COMMAND_INVALID")
                command_ttl_ms = int(
                    getattr(self._runtime.safety_limits, "autonomous_command_ttl_ms", 0)
                )
                if duration_ms <= 0 or duration_ms > command_ttl_ms:
                    self._raise_permit("SUPERVISED_TEST_COMMAND_LEASE_INVALID")
                navigation_max_speed = float(
                    getattr(getattr(self._runtime, "navigation", None), "max_speed", 0.0)
                )
                requested_speed = max(abs(left_normalized), abs(right_normalized)) * max(
                    navigation_max_speed, 0.0
                )
                if requested_speed > self._permit.max_speed_mps + 1e-9:
                    self._raise_permit("SUPERVISED_TEST_SPEED_LIMIT_EXCEEDED")
                self._permit.drive_command_count += 1
            elif command_type == "blade":
                self._permit.blade_enable_command_count += 1
            return self._permit_status_locked()

    def complete_supervised_test_permit(
        self,
        *,
        permit_token: str,
        operator_session_id: str,
        cleanup_confirmed: bool,
        cleanup_evidence: dict[str, str] | None = None,
    ) -> SupervisedTestPermitStatus:
        with self._permit_lock:
            self._require_permit_locked(
                permit_token,
                operator_session_id,
                expected_state=SupervisedTestPermitState.ACTIVE,
            )
            if not cleanup_confirmed:
                self._terminal_locked(
                    SupervisedTestPermitState.REVOKED,
                    "SUPERVISED_TEST_CLEANUP_UNCONFIRMED",
                )
                self._raise_permit("SUPERVISED_TEST_CLEANUP_UNCONFIRMED")
            assert self._permit is not None
            receipt_id = f"supervised-cleanup-{uuid4()}"
            cleanup_confirmation = {
                "source": "motor_command_gateway",
                **(cleanup_evidence or {}),
            }
            evidence_eligible = bool(
                _cleanup_confirmation_valid(cleanup_confirmation)
                and self._permit.drive_command_count > 0
                and self._permit.blade_enable_command_count > 0
            )
            receipt = {
                "receipt_schema_version": 1,
                "receipt_id": receipt_id,
                "permit_id_hash": self._permit.permit_id_hash,
                "qualification_record_id": self._permit.qualification_record_id,
                "qualification_stage_id": "supervised_blade_enabled",
                "context_binding": self._permit.context_binding,
                "physical_intervention_mechanism_hash": _sha256_text(
                    self._permit.physical_intervention_mechanism
                ),
                "cleanup_confirmed": True,
                "cleanup_confirmation": cleanup_confirmation,
                "drive_command_count": self._permit.drive_command_count,
                "blade_enable_command_count": self._permit.blade_enable_command_count,
                "eligible_for_stage_evidence": evidence_eligible,
                "completed_at": self._wall_clock().isoformat(),
            }
            self._receipts_dir.mkdir(parents=True, exist_ok=True)
            _write_json_atomic(self._receipts_dir / f"{receipt_id}.json", receipt)
            self._permit.receipt_id = receipt_id
            self._permit.receipt_evidence_eligible = evidence_eligible
            self._terminal_locked(SupervisedTestPermitState.COMPLETED, None)
            return self._permit_status_locked()

    def revoke_supervised_test_permit(
        self,
        reason_code: str = "SUPERVISED_TEST_PERMIT_REVOKED",
    ) -> SupervisedTestPermitStatus:
        with self._permit_lock:
            self._expire_locked()
            if self._permit is None:
                return SupervisedTestPermitStatus()
            if self._permit.state in _NONTERMINAL_PERMIT_STATES:
                terminal_state = (
                    SupervisedTestPermitState.EXPIRED
                    if reason_code == "SUPERVISED_TEST_PERMIT_EXPIRED"
                    else SupervisedTestPermitState.REVOKED
                )
                self._terminal_locked(terminal_state, reason_code)
            return self._permit_status_locked()

    def supervised_test_permit_status(self) -> SupervisedTestPermitStatus:
        with self._permit_lock:
            self._expire_locked()
            return self._permit_status_locked()

    def assert_supervised_test_inactive(self) -> None:
        with self._permit_lock:
            self._expire_locked()
            if self._permit and self._permit.state in _NONTERMINAL_PERMIT_STATES:
                self._raise_permit("SUPERVISED_TEST_PERMIT_ACTIVE")

    def has_active_supervised_test(self) -> bool:
        with self._permit_lock:
            self._expire_locked()
            return bool(
                self._permit
                and self._permit.state in _NONTERMINAL_PERMIT_STATES
            )

    def shutdown(self) -> SupervisedTestPermitStatus:
        return self.revoke_supervised_test_permit("SUPERVISED_TEST_BACKEND_SHUTDOWN")

    def _require_permit_locked(
        self,
        permit_token: str,
        operator_session_id: str,
        *,
        expected_state: SupervisedTestPermitState,
    ) -> None:
        self._expire_locked()
        if self._permit is None:
            self._raise_permit("SUPERVISED_TEST_PERMIT_MISSING")
        assert self._permit is not None
        if not secrets.compare_digest(self._permit.token_digest, _sha256_text(permit_token)):
            self._raise_permit("SUPERVISED_TEST_PERMIT_INVALID")
        if not secrets.compare_digest(
            self._permit.operator_session_hash,
            _sha256_text(operator_session_id),
        ):
            self._raise_permit("SUPERVISED_TEST_PERMIT_SESSION_MISMATCH")
        if self._permit.state in {
            SupervisedTestPermitState.EXPIRED,
            SupervisedTestPermitState.REVOKED,
        }:
            self._raise_permit(
                self._permit.terminal_reason_code or "SUPERVISED_TEST_PERMIT_ALREADY_USED"
            )
        if self._permit.state != expected_state:
            self._raise_permit("SUPERVISED_TEST_PERMIT_ALREADY_USED")

        context = self.build_context()
        if _context_binding(context) != self._permit.context_binding:
            self._terminal_locked(
                SupervisedTestPermitState.REVOKED,
                "SUPERVISED_TEST_PERMIT_CONTEXT_MISMATCH",
            )
            self._raise_permit("SUPERVISED_TEST_PERMIT_CONTEXT_MISMATCH")
        try:
            prerequisite = self.assert_prerequisite_current()
        except AutonomyQualificationError:
            self._terminal_locked(
                SupervisedTestPermitState.REVOKED,
                "SUPERVISED_TEST_PREREQUISITE_INVALID",
            )
            self._raise_permit("SUPERVISED_TEST_PREREQUISITE_INVALID")
        if (
            prerequisite.record is None
            or prerequisite.record.record_id != self._permit.qualification_record_id
        ):
            self._terminal_locked(
                SupervisedTestPermitState.REVOKED,
                "SUPERVISED_TEST_PERMIT_CONTEXT_MISMATCH",
            )
            self._raise_permit("SUPERVISED_TEST_PERMIT_CONTEXT_MISMATCH")

    def _expire_locked(self) -> None:
        if (
            self._permit
            and self._permit.state in _NONTERMINAL_PERMIT_STATES
            and self._monotonic() >= self._permit.expires_monotonic
        ):
            self._terminal_locked(
                SupervisedTestPermitState.EXPIRED,
                "SUPERVISED_TEST_PERMIT_EXPIRED",
            )

    def _terminal_locked(
        self,
        state: SupervisedTestPermitState,
        reason_code: str | None,
    ) -> None:
        if self._permit is None:
            return
        self._permit.state = state
        self._permit.terminal_reason_code = reason_code
        self._permit.expires_monotonic = self._monotonic()
        self._permit.expires_at = self._wall_clock()
        self._audit_permit(state.value, reason_code=reason_code)

    def _permit_status_locked(self) -> SupervisedTestPermitStatus:
        if self._permit is None:
            return SupervisedTestPermitStatus()
        remaining = (
            max(0.0, self._permit.expires_monotonic - self._monotonic())
            if self._permit.state in _NONTERMINAL_PERMIT_STATES
            else 0.0
        )
        return SupervisedTestPermitStatus(
            state=self._permit.state,
            permit_id_hash=self._permit.permit_id_hash,
            qualification_record_id=self._permit.qualification_record_id,
            issued_at=self._permit.issued_at.isoformat(),
            activated_at=(
                self._permit.activated_at.isoformat() if self._permit.activated_at else None
            ),
            expires_at=self._permit.expires_at.isoformat(),
            remaining_seconds=remaining,
            max_speed_mps=self._permit.max_speed_mps,
            max_duration_seconds=self._permit.max_duration_seconds,
            intervention_confirmed=bool(self._permit.physical_intervention_mechanism),
            cleanup_confirmed=bool(
                self._permit.state == SupervisedTestPermitState.COMPLETED
                and self._permit.receipt_id
            ),
            terminal_reason_code=self._permit.terminal_reason_code,
            receipt_id=self._permit.receipt_id,
            receipt_evidence_eligible=self._permit.receipt_evidence_eligible,
            drive_command_count=self._permit.drive_command_count,
            blade_enable_command_count=self._permit.blade_enable_command_count,
        )

    def _raise_permit(self, reason_code: str) -> None:
        self._audit_permit("denied", reason_code=reason_code)
        raise SupervisedTestPermitError(reason_code, self._permit_status_locked())

    def _evaluation_reasons(
        self,
        context: AutonomyQualificationContext,
        record: AutonomyQualificationRecord | None,
        required_stage_ids: tuple[str, ...],
        required_level: QualificationLevel,
    ) -> list[str]:
        reasons = self._context_reason_codes(context)
        if record is None:
            reasons.append("QUALIFICATION_EVIDENCE_MISSING")
            return list(dict.fromkeys(reasons))
        reasons.extend(
            self._record_reason_codes(record, context, required_stage_ids, required_level)
        )
        return list(dict.fromkeys(reasons))

    def _context_reason_codes(self, context: AutonomyQualificationContext) -> list[str]:
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
        return reasons

    def _record_reason_codes(
        self,
        record: AutonomyQualificationRecord,
        context: AutonomyQualificationContext,
        required_stage_ids: tuple[str, ...],
        required_level: QualificationLevel,
    ) -> list[str]:
        reasons: list[str] = []
        if record.schema_version != QUALIFICATION_SCHEMA_VERSION:
            reasons.append("QUALIFICATION_SCHEMA_MISMATCH")
        record_level = QualificationLevel(record.qualification_level)
        if _LEVEL_RANK[record_level] < _LEVEL_RANK[required_level]:
            if required_level == QualificationLevel.FULL_BLADE_AUTONOMY:
                reasons.append("SUPERVISED_BLADE_TEST_REQUIRED")
            else:
                reasons.append("QUALIFICATION_LEVEL_MISMATCH")
        if record.status == QualificationStageStatus.FAILED:
            reasons.append("QUALIFICATION_EVIDENCE_FAILED")
        elif record.status == QualificationStageStatus.INTERRUPTED:
            reasons.append("QUALIFICATION_EVIDENCE_INTERRUPTED")
        elif record.status != QualificationStageStatus.PASSED:
            reasons.append("QUALIFICATION_EVIDENCE_FAILED")

        created_at = _parse_iso(record.created_at)
        if created_at is None or self._wall_clock() - created_at > self._ttl:
            reasons.append("QUALIFICATION_EVIDENCE_STALE")
        if context.sim_mode or record.sim_mode:
            reasons.append("QUALIFICATION_SIMULATION_MODE")
        if context.git_tree_dirty or record.git_tree_dirty:
            reasons.append("QUALIFICATION_GIT_TREE_DIRTY")
        _append_if_mismatch(
            reasons, record.commit_sha, context.commit_sha, "QUALIFICATION_COMMIT_MISMATCH"
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
                reasons.append(
                    "SUPERVISED_BLADE_TEST_REQUIRED"
                    if stage_id == "supervised_blade_enabled"
                    else "QUALIFICATION_STAGE_MISSING"
                )
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
                self._artifact_matches_context(
                    artifact_id,
                    stage_id,
                    context,
                    record_id=record.record_id,
                )
                for artifact_id in stage.artifact_ids
            ):
                reasons.append("QUALIFICATION_STAGE_ARTIFACT_INVALID")
                if stage_id == "supervised_blade_enabled":
                    reasons.append("SUPERVISED_TEST_RECEIPT_INVALID")
        return reasons

    def _artifact_matches_context(
        self,
        artifact_id: str,
        stage_id: str,
        context: AutonomyQualificationContext,
        *,
        record_id: str,
    ) -> bool:
        try:
            payload = json.loads(
                (self._artifact_registry_dir / f"{artifact_id}.json").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError, TypeError):
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
        matches = payload.get("artifact_id") == artifact_id and all(
            metadata.get(key) == value for key, value in expected.items()
        )
        if not matches or stage_id != "supervised_blade_enabled":
            return matches
        receipt_id = metadata.get("supervised_test_receipt_id")
        return isinstance(receipt_id, str) and self._receipt_matches_context(
            receipt_id,
            context,
            record_id=record_id,
        )

    def _receipt_matches_context(
        self,
        receipt_id: str,
        context: AutonomyQualificationContext,
        *,
        record_id: str,
    ) -> bool:
        if _EVIDENCE_ID_PATTERN.fullmatch(receipt_id) is None:
            return False
        try:
            payload = json.loads(
                (self._receipts_dir / f"{receipt_id}.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError):
            return False
        matches = (
            payload.get("receipt_id") == receipt_id
            and payload.get("qualification_stage_id") == "supervised_blade_enabled"
            and payload.get("cleanup_confirmed") is True
            and payload.get("eligible_for_stage_evidence") is True
            and int(payload.get("drive_command_count") or 0) > 0
            and int(payload.get("blade_enable_command_count") or 0) > 0
            and _SHA256_PATTERN.fullmatch(
                str(payload.get("physical_intervention_mechanism_hash") or "")
            )
            is not None
            and _cleanup_confirmation_valid(payload.get("cleanup_confirmation"))
            and payload.get("context_binding") == _context_binding(context)
        )
        if not matches:
            return False
        claim_path = self._receipt_claims_dir / f"{receipt_id}.json"
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return True
        except (OSError, ValueError, TypeError):
            return False
        return claim.get("receipt_id") == receipt_id and claim.get("record_id") == record_id

    def _claim_supervised_receipts(self, record: AutonomyQualificationRecord) -> bool:
        supervised = next(
            (stage for stage in record.stages if stage.stage_id == "supervised_blade_enabled"),
            None,
        )
        if supervised is None:
            return False
        receipt_ids: list[str] = []
        for artifact_id in supervised.artifact_ids:
            try:
                payload = json.loads(
                    (self._artifact_registry_dir / f"{artifact_id}.json").read_text(
                        encoding="utf-8"
                    )
                )
                receipt_id = payload["metadata"]["supervised_test_receipt_id"]
            except (OSError, ValueError, TypeError, KeyError):
                return False
            if not isinstance(receipt_id, str) or not receipt_id:
                return False
            if _EVIDENCE_ID_PATTERN.fullmatch(receipt_id) is None:
                return False
            receipt_ids.append(receipt_id)
        if len(receipt_ids) != len(set(receipt_ids)):
            return False
        self._receipt_claims_dir.mkdir(parents=True, exist_ok=True)
        for receipt_id in receipt_ids:
            claim_path = self._receipt_claims_dir / f"{receipt_id}.json"
            claim = {"receipt_id": receipt_id, "record_id": record.record_id}
            try:
                _write_json_exclusive(claim_path, claim)
            except FileExistsError:
                try:
                    existing = json.loads(claim_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    return False
                if existing != claim:
                    return False
        return True

    def _evaluation_for(
        self,
        context: AutonomyQualificationContext,
        record: AutonomyQualificationRecord | None,
        *,
        requested_level: QualificationLevel,
        required_stage_ids: tuple[str, ...],
        reasons: list[str],
        prerequisite_reasons: list[str] | None = None,
        full_reasons: list[str] | None = None,
    ) -> AutonomyQualificationEvaluation:
        if prerequisite_reasons is None:
            prerequisite_reasons = self._evaluation_reasons(
                context,
                record,
                SUPERVISED_BLADE_TEST_PREREQUISITE_STAGES,
                QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE,
            )
        if full_reasons is None:
            full_reasons = self._evaluation_reasons(
                context,
                record,
                FULL_BLADE_AUTONOMY_REQUIRED_STAGES,
                QualificationLevel.FULL_BLADE_AUTONOMY,
            )
        diagnostic_reasons = self._evaluation_reasons(
            context,
            record,
            BLADE_OFF_DIAGNOSTIC_REQUIRED_STAGES,
            QualificationLevel.BLADE_OFF_DIAGNOSTIC,
        )
        available_level: QualificationLevel | None = None
        if not full_reasons:
            available_level = QualificationLevel.FULL_BLADE_AUTONOMY
        elif not prerequisite_reasons:
            available_level = QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE
        elif not diagnostic_reasons:
            available_level = QualificationLevel.BLADE_OFF_DIAGNOSTIC
        unique_reasons = list(dict.fromkeys(reasons))
        return AutonomyQualificationEvaluation(
            ok=not unique_reasons,
            reason_codes=unique_reasons,
            remediation=_remediation(unique_reasons),
            generated_at=self._wall_clock().isoformat(),
            required_stage_ids=list(required_stage_ids),
            requested_level=requested_level,
            available_level=available_level,
            prerequisite_ok=not prerequisite_reasons,
            prerequisite_reason_codes=list(dict.fromkeys(prerequisite_reasons)),
            full_autonomy_ok=not full_reasons,
            full_autonomy_reason_codes=list(dict.fromkeys(full_reasons)),
            camera_ai_safety_role="advisory",
            context=context,
            record=record,
            permit=self.supervised_test_permit_status(),
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

    def _audit_permit(self, event: str, *, reason_code: str | None = None) -> None:
        permit = self._permit
        if permit is not None:
            binding = permit.context_binding
        else:
            try:
                binding = _context_binding(self.build_context())
            except Exception:
                binding = {}
        self._audit(
            f"qualification.supervised_permit.{event}",
            permit_id_hash=permit.permit_id_hash if permit else None,
            qualification_record_id=permit.qualification_record_id if permit else None,
            qualification_level=QualificationLevel.SUPERVISED_BLADE_TEST_PREREQUISITE.value,
            stage_id="supervised_blade_enabled",
            reason_code=reason_code,
            commit_sha=binding.get("commit_sha"),
            hardware_config_hash=binding.get("hardware_config_hash"),
            limits_hash=binding.get("limits_hash"),
            runtime_identity_hash=binding.get("runtime_identity_hash"),
            robohat_firmware_version=binding.get("robohat_firmware_version"),
            operator_confirmed=bool(permit),
            local_supervision_confirmed=bool(permit),
            intervention_confirmed=bool(
                permit and permit.physical_intervention_mechanism
            ),
            physical_intervention_mechanism_hash=(
                _sha256_text(permit.physical_intervention_mechanism)
                if permit and permit.physical_intervention_mechanism
                else None
            ),
            operator_id=permit.operator_id if permit else None,
            cleanup_confirmed=bool(
                permit and permit.state == SupervisedTestPermitState.COMPLETED
            ),
            receipt_id=permit.receipt_id if permit else None,
            receipt_evidence_eligible=(
                permit.receipt_evidence_eligible if permit else False
            ),
        )

    def _audit(self, action: str, **details: Any) -> None:
        safe_details = {key: value for key, value in details.items() if value is not None}
        logger.info("%s %s", action, safe_details)
        persistence = getattr(self._runtime, "persistence", None)
        add_audit_log = getattr(persistence, "add_audit_log", None)
        if callable(add_audit_log):
            try:
                add_audit_log(action, details=safe_details)
            except TypeError:
                # Lightweight test doubles may expose only positional arguments.
                try:
                    add_audit_log(action, None, None, safe_details)
                except Exception:
                    logger.exception("qualification audit persistence failed")
            except Exception:
                logger.exception("qualification audit persistence failed")


def _level_for_stages(
    required_stage_ids: tuple[str, ...],
    fallback: QualificationLevel,
) -> QualificationLevel:
    for level, stages in _LEVEL_STAGES.items():
        if tuple(required_stage_ids) == stages:
            return level
    return fallback


def _context_binding(context: AutonomyQualificationContext) -> dict[str, Any]:
    return {
        "schema_version": context.schema_version,
        "commit_sha": context.commit_sha,
        "git_tree_dirty": context.git_tree_dirty,
        "hardware_config_hash": context.hardware_config_hash,
        "limits_hash": context.limits_hash,
        "runtime_identity_hash": context.runtime_identity_hash,
        "sim_mode": context.sim_mode,
        "robohat_firmware_version": context.robohat_firmware_version,
    }


def _cleanup_confirmation_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(
        value.get("source") == "motor_command_gateway"
        and isinstance(value.get("drive_audit_id"), str)
        and value.get("drive_audit_id")
        and value.get("drive_status") == "accepted"
        and isinstance(value.get("blade_audit_id"), str)
        and value.get("blade_audit_id")
        and value.get("blade_status") == "accepted"
    )


def _remediation(reason_codes: list[str]) -> dict[str, str]:
    return {
        code: REMEDIATION.get(code, "Review autonomy qualification evidence.")
        for code in reason_codes
    }


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


def _write_json_exclusive(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True))


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
