"""Odometry calculator (T059)

Provides simple differential drive dead-reckoning utilities. This module is
SIM_MODE-safe and does not access hardware directly; it consumes wheel encoder
tick deltas (if available) or integrates commanded velocities for short
intervals as a fallback. It is intentionally lightweight for Raspberry Pi 4/5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class WheelParams:
    wheel_radius_m: float = 0.05  # 10cm diameter wheel
    wheel_base_m: float = 0.30  # distance between wheels
    ticks_per_rev: int = 1024


def integrate_from_ticks(
    left_ticks: int,
    right_ticks: int,
    params: WheelParams,
) -> tuple[float, float]:
    """Convert tick deltas to linear distance (m) and heading change (deg).

    Returns (distance_m, delta_heading_deg).
    """
    # Convert ticks to wheel angle (radians)
    left_rad = (left_ticks / params.ticks_per_rev) * 2 * math.pi
    right_rad = (right_ticks / params.ticks_per_rev) * 2 * math.pi
    # Convert to arc length
    left_dist = left_rad * params.wheel_radius_m
    right_dist = right_rad * params.wheel_radius_m
    # Differential drive kinematics
    distance = (left_dist + right_dist) / 2.0
    delta_theta_rad = (right_dist - left_dist) / params.wheel_base_m
    delta_heading_deg = math.degrees(delta_theta_rad)
    return distance, delta_heading_deg


def integrate_velocity(
    linear_mps: float,
    angular_dps: float,
    dt_s: float,
) -> tuple[float, float]:
    """Integrate commanded velocity over dt.

    Returns (distance_m, delta_heading_deg).
    """
    return max(0.0, linear_mps) * dt_s, angular_dps * dt_s


class OdometryIntegrator:
    """Stateful wrapper around integrate_from_ticks / integrate_velocity.

    Call step_ticks() when encoder ticks are available.
    Call step_velocity() as a fallback (e.g. commanded speed + elapsed time).
    Both return (distance_m, delta_heading_deg) and advance internal state.

    The integrator does NOT produce absolute pose; it produces incremental
    odometry for the PoseFilter predict step.
    """

    def __init__(self, params: WheelParams | None = None) -> None:
        self._params = params or WheelParams()
        self._last_left_ticks: int | None = None
        self._last_right_ticks: int | None = None

    def step_ticks(
        self,
        left_ticks_absolute: int,
        right_ticks_absolute: int,
    ) -> tuple[float, float]:
        """Compute (distance_m, delta_heading_deg) from absolute tick counters.

        On the first call (no previous ticks), returns (0.0, 0.0).
        """
        if self._last_left_ticks is None:
            self._last_left_ticks = left_ticks_absolute
            self._last_right_ticks = right_ticks_absolute
            return 0.0, 0.0

        delta_left = left_ticks_absolute - self._last_left_ticks
        delta_right = right_ticks_absolute - (self._last_right_ticks or 0)
        self._last_left_ticks = left_ticks_absolute
        self._last_right_ticks = right_ticks_absolute
        return integrate_from_ticks(delta_left, delta_right, self._params)

    def step_velocity(
        self,
        linear_mps: float,
        angular_dps: float,
        dt_s: float,
    ) -> tuple[float, float]:
        """Compute (distance_m, delta_heading_deg) from commanded velocity.

        This is the dead-reckoning fallback when encoder ticks are unavailable.
        Never returns a fixed constant — distance is always velocity × time.
        """
        return integrate_velocity(linear_mps, angular_dps, dt_s)

    def reset_ticks(self) -> None:
        """Clear stored tick state (call on mission start)."""
        self._last_left_ticks = None
        self._last_right_ticks = None


__all__ = [
    "WheelParams",
    "integrate_from_ticks",
    "integrate_velocity",
    "OdometryIntegrator",
]
