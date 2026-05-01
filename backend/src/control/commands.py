from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


@dataclass
class DriveCommand:
    left: float
    right: float
    source: str          # "manual" | "mission" | "diagnosis" | "legacy"
    duration_ms: int
    session_id: str | None = None
    max_speed_limit: float = 0.8
    legacy: bool = False


@dataclass
class BladeCommand:
    active: bool
    source: str          # "manual" | "mission"
    session_id: str | None = None
    motors_active: bool = False


@dataclass
class EmergencyTrigger:
    reason: str
    source: str          # "operator" | "navigation" | "safety_trigger"
    request: Any | None = None


@dataclass
class EmergencyClear:
    confirmed: bool
    operator: str | None = None


class CommandStatus(str, Enum):
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    QUEUED = "queued"
    TIMED_OUT = "timed_out"
    ACK_FAILED = "ack_failed"
    EMERGENCY_LATCHED = "emergency_latched"
    FIRMWARE_UNKNOWN = "firmware_unknown"
    FIRMWARE_INCOMPATIBLE = "firmware_incompatible"


@dataclass
class DriveOutcome:
    status: CommandStatus
    audit_id: str
    status_reason: str | None
    active_interlocks: list[str]
    watchdog_latency_ms: float | None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class BladeOutcome:
    status: CommandStatus
    audit_id: str
    status_reason: str | None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class EmergencyOutcome:
    status: CommandStatus
    audit_id: str
    hardware_confirmed: bool
    idempotent: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
