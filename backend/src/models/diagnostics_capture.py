"""Telemetry capture record models.

These types define the on-disk format used by the replay harness. The format is
JSONL (one JSON object per line). See docs/diagnostics-replay.md.

`NavigationStateSnapshot` is a trimmed projection of NavigationState. It
deliberately omits planned_path, obstacle_map, coverage_grid, and
safety_boundaries because those are large and slow-changing. Replay parity is
checked against the dynamic fields below, which is sufficient to detect
behavior changes in update_navigation_state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.src.models.navigation_state import NavigationMode, PathStatus, Position
from backend.src.models.sensor_data import SensorData

CAPTURE_SCHEMA_VERSION: int = 1

RecordType = Literal["nav_step"]


class NavigationStateSnapshot(BaseModel):
    """Trimmed projection of NavigationState for replay parity comparison."""

    current_position: Position | None = None
    heading: float | None = None
    gps_cog: float | None = None
    velocity: float | None = None
    target_velocity: float | None = None
    current_waypoint_index: int = 0
    path_status: PathStatus = PathStatus.PLANNING
    navigation_mode: NavigationMode = NavigationMode.IDLE
    dead_reckoning_active: bool = False
    dead_reckoning_drift: float | None = None
    last_gps_fix: datetime | None = None
    timestamp: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)


class CaptureRecord(BaseModel):
    """One captured navigation step.

    The pair (sensor_data, navigation_state_after) is sufficient to replay
    a step: feed sensor_data into a fresh NavigationService, then compare its
    produced navigation_state against navigation_state_after.
    """

    capture_version: int
    record_type: RecordType
    sensor_data: SensorData
    navigation_state_after: NavigationStateSnapshot

    model_config = ConfigDict(use_enum_values=True)


__all__ = [
    "CAPTURE_SCHEMA_VERSION",
    "CaptureRecord",
    "NavigationStateSnapshot",
    "RecordType",
]
