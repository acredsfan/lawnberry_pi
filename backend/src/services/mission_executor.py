"""MissionExecutor — owns mission lifecycle and waypoint traversal loop.

Accepts localization and motor gateway as constructor dependencies so it can
be tested with fakes, without constructing NavigationService or touching
hardware.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..models import NavigationMode, PathStatus, Position, Waypoint
from ..nav.waypoint_geometry import (
    compute_blend_speeds,
    compute_tank_speeds,
    heading_error,
    is_in_tank_mode,
)
from ..nav.path_planner import PathPlanner
from ..nav.geoutils import point_in_polygon

if TYPE_CHECKING:
    from ..models.mission import Mission, MissionWaypoint
    from ..protocols.mission import MissionStatusReader

logger = logging.getLogger(__name__)


class MissionExecutor:
    """Owns mission lifecycle traversal and waypoint-to-motion conversion.

    Args:
        localization: Any object satisfying LocalizationProvider protocol.
            Must expose: current_position, heading, dead_reckoning_active,
            last_gps_fix.
        gateway: Any object satisfying the drive interface.
            Must expose: is_emergency_active() -> bool,
            dispatch_drive_speeds(left, right) -> Awaitable[bool].
        max_speed: Maximum wheel speed (m/s-equivalent, default 0.8).
        cruise_speed: Default forward speed (m/s-equivalent, default 0.5).
        waypoint_tolerance: Arrival radius in metres (default 0.5).
        max_waypoint_fix_age_seconds: GPS staleness threshold (default 2.0).
        max_waypoint_accuracy_m: GPS accuracy floor in metres (default 5.0).
        position_verification_timeout_seconds: Abort timeout (default 30.0).
    """

    def __init__(
        self,
        *,
        localization: Any,
        gateway: Any,
        max_speed: float = 0.8,
        cruise_speed: float = 0.5,
        waypoint_tolerance: float = 0.5,
        max_waypoint_fix_age_seconds: float = 2.0,
        max_waypoint_accuracy_m: float = 5.0,
        position_verification_timeout_seconds: float = 30.0,
    ) -> None:
        self._loc = localization
        self._gw = gateway
        self.max_speed = max_speed
        self.cruise_speed = cruise_speed
        self.waypoint_tolerance = waypoint_tolerance
        self.max_waypoint_fix_age_seconds = max_waypoint_fix_age_seconds
        self.max_waypoint_accuracy_m = max_waypoint_accuracy_m
        self.position_verification_timeout_seconds = position_verification_timeout_seconds
        self._path_planner = PathPlanner()
        # Mutable mission state — reset by execute_mission()
        self.current_waypoint_index: int = 0
        self._active: bool = False
        self._failure_detail: str | None = None
