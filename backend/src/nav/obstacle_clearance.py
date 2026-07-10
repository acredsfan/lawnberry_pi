from __future__ import annotations

from typing import Any


def configured_tof_obstacle_threshold_m(limits: Any) -> float:
    """Return the operator-configured near-field ToF obstacle threshold."""

    return max(0.0, float(getattr(limits, "tof_obstacle_distance_meters", 0.2)))


def required_obstacle_clearance_m(speed_mps: float | None, limits: Any) -> float:
    """Return stopping clearance measured forward from the ToF sensor face.

    ``obstacle_front_offset_m`` describes where the sensor is mounted relative
    to the mower center. It is useful for body geometry, but adding it here
    would double-count distance because the ToF measurement already starts at
    the front sensor.
    """

    if not hasattr(limits, "obstacle_min_clearance_m"):
        return configured_tof_obstacle_threshold_m(limits)

    if speed_mps is None:
        speed = float(getattr(limits, "obstacle_conservative_unknown_speed_mps", 0.4))
    else:
        speed = max(0.0, abs(float(speed_mps)))
    latency = float(getattr(limits, "obstacle_detection_latency_s", 0.35))
    decel = float(getattr(limits, "obstacle_conservative_deceleration_mps2", 0.45))
    margin = float(getattr(limits, "obstacle_fixed_margin_m", 0.10))
    floor = float(getattr(limits, "obstacle_min_clearance_m", 0.15))
    stopping = speed * latency + (speed * speed) / (2.0 * decel)
    return max(floor, stopping + margin)
