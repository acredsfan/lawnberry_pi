from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

QUALIFICATION_SCHEMA_VERSION = 2
EvidenceId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


class QualificationStageStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"
    OPERATOR_REQUIRED = "operator_required"


class QualificationLevel(str, Enum):
    """Evidence levels in increasing order of hazardous authority."""

    BLADE_OFF_DIAGNOSTIC = "blade_off_diagnostic"
    SUPERVISED_BLADE_TEST_PREREQUISITE = "supervised_blade_test_prerequisite"
    FULL_BLADE_AUTONOMY = "full_blade_autonomy"


class SupervisedTestPermitState(str, Enum):
    """Public, non-secret permit lifecycle state."""

    ABSENT = "absent"
    ISSUED = "issued"
    ACTIVE = "active"
    COMPLETED = "completed"
    REVOKED = "revoked"
    EXPIRED = "expired"


class AutonomyQualificationStageResult(BaseModel):
    stage_id: str
    status: QualificationStageStatus
    started_at: str | None = None
    completed_at: str | None = None
    reason_code: str | None = None
    summary: str = ""
    artifact_ids: list[EvidenceId] = Field(default_factory=list)
    measurements: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class AutonomyQualificationContext(BaseModel):
    schema_version: int = QUALIFICATION_SCHEMA_VERSION
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    commit_sha: str | None = None
    git_tree_dirty: bool = False
    hardware_config_hash: str | None = None
    limits_hash: str | None = None
    runtime_identity_hash: str
    pi_model: str = "unknown"
    hostname_hash: str
    machine_id_hash: str | None = None
    os_release: str = "unknown"
    sim_mode: bool = True
    robohat_firmware_version: str | None = None


class AutonomyQualificationRecord(BaseModel):
    schema_version: int = QUALIFICATION_SCHEMA_VERSION
    record_id: EvidenceId = Field(default_factory=lambda: str(uuid4()))
    qualification_level: QualificationLevel = QualificationLevel.BLADE_OFF_DIAGNOSTIC
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: QualificationStageStatus = QualificationStageStatus.INTERRUPTED
    commit_sha: str | None = None
    git_tree_dirty: bool = False
    hardware_config_hash: str | None = None
    limits_hash: str | None = None
    runtime_identity_hash: str
    pi_model: str = "unknown"
    hostname_hash: str
    machine_id_hash: str | None = None
    os_release: str = "unknown"
    sim_mode: bool = True
    robohat_firmware_version: str | None = None
    stages: list[AutonomyQualificationStageResult] = Field(default_factory=list)
    artifact_ids: list[EvidenceId] = Field(default_factory=list)
    operator_id: str | None = None
    notes: str = ""

    model_config = ConfigDict(use_enum_values=True)


class AutonomyQualificationEvaluation(BaseModel):
    ok: bool
    reason_codes: list[str] = Field(default_factory=list)
    remediation: dict[str, str] = Field(default_factory=dict)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    required_stage_ids: list[str] = Field(default_factory=list)
    requested_level: QualificationLevel = QualificationLevel.FULL_BLADE_AUTONOMY
    available_level: QualificationLevel | None = None
    prerequisite_ok: bool = False
    prerequisite_reason_codes: list[str] = Field(default_factory=list)
    full_autonomy_ok: bool = False
    full_autonomy_reason_codes: list[str] = Field(default_factory=list)
    camera_ai_safety_role: Literal["advisory"] = "advisory"
    context: AutonomyQualificationContext
    record: AutonomyQualificationRecord | None = None
    permit: SupervisedTestPermitStatus | None = None

    model_config = ConfigDict(use_enum_values=True)


class SupervisedTestPermitStatus(BaseModel):
    """Redacted permit status. The reusable bearer token is never returned here."""

    state: SupervisedTestPermitState = SupervisedTestPermitState.ABSENT
    permit_id_hash: str | None = None
    qualification_record_id: EvidenceId | None = None
    stage_id: Literal["supervised_blade_enabled"] = "supervised_blade_enabled"
    issued_at: str | None = None
    activated_at: str | None = None
    expires_at: str | None = None
    remaining_seconds: float = 0.0
    max_speed_mps: float = 0.0
    max_duration_seconds: float = 0.0
    intervention_confirmed: bool = False
    cleanup_confirmed: bool = False
    terminal_reason_code: str | None = None
    receipt_id: EvidenceId | None = None
    receipt_evidence_eligible: bool = False
    drive_command_count: int = 0
    blade_enable_command_count: int = 0

    model_config = ConfigDict(use_enum_values=True)


class SupervisedTestPermitIssueRequest(BaseModel):
    operator_confirmed: bool
    local_supervision_confirmed: bool
    physical_intervention_mechanism: str = Field(min_length=8, max_length=256)


class SupervisedTestPermitTokenRequest(BaseModel):
    permit_token: SecretStr = Field(min_length=32, max_length=512, repr=False)


class SupervisedTestDriveRequest(SupervisedTestPermitTokenRequest):
    left_normalized: float = Field(ge=-1.0, le=1.0)
    right_normalized: float = Field(ge=-1.0, le=1.0)
    duration_ms: int = Field(ge=50, le=2000)


class SupervisedTestBladeRequest(SupervisedTestPermitTokenRequest):
    active: bool


class SupervisedTestCompleteRequest(SupervisedTestPermitTokenRequest):
    cleanup_confirmed: bool


class SupervisedTestRevokeRequest(BaseModel):
    reason: Literal[
        "operator_requested",
        "test_interrupted",
        "unsafe_condition",
        "cleanup_requested",
    ] = "operator_requested"


class SupervisedTestPermitIssueResponse(BaseModel):
    permit_token: str = Field(
        repr=False,
        json_schema_extra={"format": "password", "readOnly": True},
    )
    status: SupervisedTestPermitStatus
