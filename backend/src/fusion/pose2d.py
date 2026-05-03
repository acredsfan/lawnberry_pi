"""Canonical pose output type for LocalizationService.

Pose2D is the single source of truth for robot position and heading
inside the navigation stack. NavigationService consumes Pose2D rather
than raw GPS dictionaries (§3 acceptance criterion).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PoseQuality(str, Enum):
    """Ordered quality states for the current pose estimate.

    Higher ordinal = more trustworthy. Code may compare with < / > after
    converting to list index if ordering matters.
    """
    RTK_FIXED     = "rtk_fixed"      # GPS RTK fixed, cm-level
    GPS_FLOAT     = "gps_float"      # GPS float / SBAS, sub-metre
    GPS_DEGRADED  = "gps_degraded"   # GPS standalone, metres-level accuracy
    DEAD_RECKONING = "dead_reckoning" # No fresh GPS; encoder/velocity odometry
    STALE         = "stale"          # No update for > STALE_THRESHOLD_S seconds


STALE_THRESHOLD_S: float = 5.0


@dataclass
class Pose2D:
    """Local-frame pose in the ENU frame anchored at mission start.

    x_m: east displacement in metres from origin
    y_m: north displacement in metres from origin
    heading_deg: compass heading, 0 = north, 90 = east, clockwise-positive
    velocity_mps: forward speed in m/s (scalar, non-negative)
    angular_velocity_dps: yaw rate in deg/s, clockwise-positive
    quality: current trustworthiness level
    gps_timestamp_s: monotonic time of last GPS measurement update (None if never)
    imu_timestamp_s: monotonic time of last IMU measurement update (None if never)
    encoder_timestamp_s: monotonic time of last encoder odometry update (None if never)
    filter_timestamp_s: monotonic time of last predict step
    """
    x_m: float = 0.0
    y_m: float = 0.0
    heading_deg: float = 0.0
    velocity_mps: float = 0.0
    angular_velocity_dps: float = 0.0
    quality: PoseQuality = PoseQuality.STALE
    gps_timestamp_s: float | None = None
    imu_timestamp_s: float | None = None
    encoder_timestamp_s: float | None = None
    filter_timestamp_s: float = field(default_factory=lambda: 0.0)

    def distance_to(self, other: "Pose2D") -> float:
        """Euclidean distance in metres between two poses."""
        return ((self.x_m - other.x_m) ** 2 + (self.y_m - other.y_m) ** 2) ** 0.5

    def heading_error_deg(self, target_deg: float) -> float:
        """Signed shortest angular error from self.heading_deg to target_deg."""
        return ((target_deg - self.heading_deg + 180.0) % 360.0) - 180.0


__all__ = ["Pose2D", "PoseQuality", "STALE_THRESHOLD_S"]
