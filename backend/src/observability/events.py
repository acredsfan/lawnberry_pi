"""Structured observability event models for the LawnBerry navigation/control stack."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class PersistenceMode(str, Enum):
    """Controls which events are written to SQLite.

    Read from the LAWNBERRY_PERSISTENCE_MODE environment variable at startup.
    Defaults to 'summary' to keep SD-card write rates acceptable during
    unattended field operation.
    """
    FULL = "full"
    SUMMARY = "summary"


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PoseUpdated:
    """Emitted by NavigationService on each successful pose update."""

    run_id: str
    mission_id: str
    lat: float
    lon: float
    heading_deg: float
    pose_quality: str           # "rtk_fixed" | "gps_float" | "gps_degraded" | "dead_reckoning" | "stale"
    source: str                 # "gps" | "dead_reckoning" | "encoder"
    accuracy_m: float | None = None
    velocity_mps: float | None = None
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="pose_updated", init=False)


@dataclass(frozen=True)
class HeadingAligned:
    """Emitted when the GPS COG heading bootstrap completes (first stable snap)."""

    run_id: str
    mission_id: str
    aligned_heading_deg: float
    sample_count: int           # Always 1 at first snap; may increase in future
    alignment_source: str       # "gps_cog_snap" | "imu_calibrated"
    delta_applied_deg: float | None = None
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="heading_aligned", init=False)


@dataclass(frozen=True)
class WaypointTargetChanged:
    """Emitted by MissionService/NavigationService when a new waypoint becomes the target."""

    run_id: str
    mission_id: str
    waypoint_index: int
    waypoint_lat: float
    waypoint_lon: float
    distance_to_target_m: float
    previous_index: int | None = None
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="waypoint_target_changed", init=False)


@dataclass(frozen=True)
class MotionCommandIssued:
    """Emitted by MotorCommandGateway immediately before dispatching to RoboHAT."""

    run_id: str
    mission_id: str
    audit_id: str
    left: float
    right: float
    source: str                 # "manual" | "mission" | "diagnosis"
    duration_ms: int
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="motion_command_issued", init=False)


@dataclass(frozen=True)
class MotionCommandAcked:
    """Emitted by MotorCommandGateway after RoboHAT acknowledges a command."""

    run_id: str
    mission_id: str
    audit_id: str
    watchdog_latency_ms: float
    hardware_confirmed: bool
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="motion_command_acked", init=False)


@dataclass(frozen=True)
class SafetyGateBlocked:
    """Emitted by MotorCommandGateway when a command is rejected by a safety interlock."""

    run_id: str
    mission_id: str
    audit_id: str
    reason: str                 # human-readable reason string
    interlocks: list[str]       # list of active interlock names
    source: str                 # command source that was blocked
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="safety_gate_blocked", init=False)


@dataclass(frozen=True)
class MissionStateChanged:
    """Emitted by MissionService on start, pause, resume, abort, or complete."""

    run_id: str
    mission_id: str
    previous_state: str
    new_state: str
    detail: str
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = field(default="mission_state_changed", init=False)


# Type alias for all domain events
DomainEvent = (
    PoseUpdated
    | HeadingAligned
    | WaypointTargetChanged
    | MotionCommandIssued
    | MotionCommandAcked
    | SafetyGateBlocked
    | MissionStateChanged
)

# Events always persisted in summary mode
SUMMARY_MODE_EVENTS: frozenset[str] = frozenset(
    {"mission_state_changed", "safety_gate_blocked"}
)
