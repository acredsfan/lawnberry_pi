"""Pure stateless waypoint geometry helpers.

All functions are side-effect-free and depend only on their arguments.
They can be imported and tested without constructing any service object.
"""
from __future__ import annotations


def heading_error(target: float, current: float) -> float:
    """Return the signed shortest heading delta from *current* to *target* (degrees).

    Positive = clockwise (right turn needed).
    Negative = counter-clockwise (left turn needed).
    Result is in [-180, +180).
    """
    return (target - current + 180.0) % 360.0 - 180.0


def is_in_tank_mode(abs_error: float, *, currently_in_tank: bool) -> bool:
    """Apply hysteresis for tank vs blended drive mode.

    Enter tank-turn at >70°; exit when error drops below 50°.
    This prevents mode flapping near the boundary.
    """
    if abs_error > 70.0:
        return True
    if currently_in_tank and abs_error >= 50.0:
        return True
    return False


def compute_tank_speeds(
    heading_err: float,
    *,
    max_speed: float,
    stall_boost: float,
) -> tuple[float, float]:
    """Compute counter-rotating (tank-turn) wheel speeds.

    Args:
        heading_err: Signed heading error in degrees (positive = CW).
        max_speed: Maximum wheel speed magnitude (m/s equivalent).
        stall_boost: Extra speed fraction (0-0.6) to overcome motor stall.

    Returns:
        (left_speed, right_speed) in the same units as max_speed.
        CW turn (heading_err > 0): left > 0, right < 0.
        CCW turn (heading_err < 0): left < 0, right > 0.
    """
    if heading_err == 0.0:
        return 0.0, 0.0
    turn_sign = 1.0 if heading_err > 0 else -1.0
    turn_speed = min(max_speed, 0.5 + stall_boost)
    left_speed = turn_sign * turn_speed
    right_speed = -turn_sign * turn_speed
    left_speed = max(-max_speed, min(max_speed, left_speed))
    right_speed = max(-max_speed, min(max_speed, right_speed))
    return left_speed, right_speed


def compute_blend_speeds(
    heading_err: float,
    *,
    base_speed: float,
    stall_boost: float,
    max_speed: float = 0.8,
    in_heading_bootstrap: bool = False,
) -> tuple[float, float]:
    """Compute blended (forward + proportional turn) wheel speeds.

    Args:
        heading_err: Signed heading error in degrees (positive = CW).
        base_speed: Desired forward speed before corrections.
        stall_boost: Unused in blend mode; present for API symmetry.
        max_speed: Speed ceiling for clamping.
        in_heading_bootstrap: When True, enforce a minimum forward speed
            so GPS COG activates quickly during the heading bootstrap drive.

    Returns:
        (left_speed, right_speed).
        CW (heading_err > 0): left > right.
        CCW (heading_err < 0): right > left.
    """
    abs_err = abs(heading_err)
    turn_effort = max(-1.0, min(1.0, heading_err / 45.0))
    forward_speed = base_speed

    if abs_err > 10:
        taper = max(0.7, 1.0 - abs_err / 200.0)
        forward_speed *= taper

    if in_heading_bootstrap:
        forward_speed = max(forward_speed, 0.15)

    forward_speed = max(forward_speed, 0.3)

    left_speed = forward_speed + turn_effort * forward_speed
    right_speed = forward_speed - turn_effort * forward_speed

    inner_min = base_speed * 0.2
    if turn_effort > 0:
        right_speed = max(right_speed, inner_min)
    elif turn_effort < 0:
        left_speed = max(left_speed, inner_min)

    left_speed = max(-max_speed, min(max_speed, left_speed))
    right_speed = max(-max_speed, min(max_speed, right_speed))
    return left_speed, right_speed
