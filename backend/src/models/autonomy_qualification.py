from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

QUALIFICATION_SCHEMA_VERSION = 1
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
    context: AutonomyQualificationContext
    record: AutonomyQualificationRecord | None = None
