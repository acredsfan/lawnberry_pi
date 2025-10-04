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
    wheel_base_m: float = 0.30    # distance between wheels
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


__all__ = [
    "WheelParams",
    "integrate_from_ticks",
    "integrate_velocity",
]
