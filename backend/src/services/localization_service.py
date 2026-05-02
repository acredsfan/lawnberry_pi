"""LocalizationService — owns current pose, GPS/IMU/encoder fusion, antenna
offset, GPS age/accuracy policy, pose quality, and mission-start heading
bootstrap.

Extracted from the 1910-line NavigationService per §2 of the architecture
plan (docs/major-architecture-and-code-improvement-plan.md).

The legacy NavigationService path remains intact when USE_LEGACY_NAVIGATION=1.
When the env var is absent or 0, NavigationService delegates localization
responsibilities to this service.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..models import Position, SensorData
from ..nav.geoutils import haversine_m
from ..nav.localization_helpers import (
    apply_antenna_offset,
    heading_delta,
    resolve_gps_cog_from_inputs,
    wrap_heading,
)
from ..nav.path_planner import PathPlanner

logger = logging.getLogger(__name__)


class PoseQuality(str, Enum):
    """Coarse pose quality classification visible in telemetry and Mission Planner.

    rtk_fixed      — RTK-fixed GPS, sub-centimetre horizontal accuracy.
    gps_float      — GPS float/DGPS, accuracy < configured threshold.
    gps_degraded   — GPS available but accuracy exceeds threshold.
    dead_reckoning — GPS missing; odometry/IMU integration only.
    stale          — No usable position or heading data.
    """
    RTK_FIXED = "rtk_fixed"
    GPS_FLOAT = "gps_float"
    GPS_DEGRADED = "gps_degraded"
    DEAD_RECKONING = "dead_reckoning"
    STALE = "stale"


class LocalizationState:
    """Mutable pose state owned exclusively by LocalizationService.

    Not a Pydantic model: mutable hot-path state that is updated at 5 Hz
    should not pay Pydantic validation overhead on every field write.
    """

    __slots__ = (
        "current_position",
        "heading",
        "gps_cog",
        "velocity",
        "quality",
        "dead_reckoning_active",
        "dead_reckoning_drift",
        "last_gps_fix",
        "timestamp",
    )

    def __init__(self) -> None:
        self.current_position: Position | None = None
        self.heading: float | None = None          # compass degrees, IMU-derived
        self.gps_cog: float | None = None          # GPS course-over-ground degrees
        self.velocity: float | None = None         # m/s
        self.quality: PoseQuality = PoseQuality.STALE
        self.dead_reckoning_active: bool = False
        self.dead_reckoning_drift: float | None = None  # metres estimated drift
        self.last_gps_fix: datetime | None = None
        self.timestamp: datetime = datetime.now(UTC)
