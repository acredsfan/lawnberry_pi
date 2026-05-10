"""Pure stateless waypoint geometry helpers — heading error, drive mixing, and
Stanley path-tracking.

All functions are side-effect-free and depend only on their arguments.
They can be imported and tested without constructing any service object.
"""
from __future__ import annotations

import math


def heading_error(target: float, current: float) -> float:
    """Return the signed shortest heading delta from *current* to *target* (degrees).

    Positive = clockwise (right turn needed).
    Negative = counter-clockwise (left turn needed).
    Result is in [-180, +180).
    """
    return (target - current + 180.0) % 360.0 - 180.0


def is_in_tank_mode(abs_error: float, *, currently_in_tank: bool) -> bool:
    """Apply hysteresis for tank vs blended drive mode.

    Enter tank-turn at >60°; exit when error drops below 50°.
    This prevents mode flapping near the boundary.
    """
    if abs_error > 60.0:
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
        stall_boost: Stall-escape boost (0–0.6) from the stall detector.
            Scales forward_speed by (1 + stall_boost) and raises the inner
            wheel floor so both wheels stay above stiction on grass.
        max_speed: Speed ceiling for clamping.
        in_heading_bootstrap: When True, enforce a minimum forward speed
            so GPS COG activates quickly during the heading bootstrap drive.

    Returns:
        (left_speed, right_speed).
        CW (heading_err > 0): left > right.
        CCW (heading_err < 0): right > left.
    """
    abs_err = abs(heading_err)
    turn_effort = max(-1.0, min(1.0, heading_err / 90.0))
    forward_speed = base_speed

    if abs_err > 10:
        taper = max(0.7, 1.0 - abs_err / 200.0)
        forward_speed *= taper

    if in_heading_bootstrap:
        forward_speed = max(forward_speed, 0.15)

    forward_speed = max(forward_speed, 0.3)

    if stall_boost > 0.0:
        forward_speed = min(max_speed, forward_speed * (1.0 + stall_boost))

    left_speed = forward_speed + turn_effort * forward_speed
    right_speed = forward_speed - turn_effort * forward_speed

    inner_min = base_speed * (0.2 + stall_boost)
    if turn_effort > 0:
        right_speed = max(right_speed, inner_min)
    elif turn_effort < 0:
        left_speed = max(left_speed, inner_min)

    left_speed = max(-max_speed, min(max_speed, left_speed))
    right_speed = max(-max_speed, min(max_speed, right_speed))
    return left_speed, right_speed


def cross_track_error(
    point: tuple[float, float],
    line_a: tuple[float, float],
    line_b: tuple[float, float],
) -> float:
    """Signed perpendicular distance (metres) from *point* to the line A→B.

    Positive = point is to the RIGHT of the line when walking from A to B.
    Uses a flat-Earth ENU projection anchored at *line_a* (accurate to ~20 km).

    Args:
        point:  (latitude, longitude) of the current position.
        line_a: (latitude, longitude) of the path segment start.
        line_b: (latitude, longitude) of the path segment end.
    """
    lat_a, lon_a = line_a
    _MPD_LAT = 111_320.0
    mpd_lon = _MPD_LAT * math.cos(math.radians(lat_a))

    north_p = (point[0] - lat_a) * _MPD_LAT
    east_p = (point[1] - lon_a) * mpd_lon

    north_b = (line_b[0] - lat_a) * _MPD_LAT
    east_b = (line_b[1] - lon_a) * mpd_lon

    path_len = math.hypot(east_b, north_b)
    if path_len < 1e-9:
        return 0.0

    # Unit path vector (east, north component)
    ue = east_b / path_len
    un = north_b / path_len

    # Positive = right of path (2D right-hand rule: un*east_p - ue*north_p)
    return un * east_p - ue * north_p


def stanley_steer(
    heading_err_deg: float,
    cte_m: float,
    velocity_mps: float,
    *,
    k_cte: float = 0.6,
    v_floor: float = 0.2,
    max_steer_deg: float = 60.0,
    dead_band_m: float = 0.1,
) -> float:
    """Stanley path-tracking steer command (degrees).

    Positive = right turn needed; negative = left turn needed.

    Combines a path-heading error with a cross-track-error correction:
        steer = heading_err - atan(k_cte * cte / max(v, v_floor))

    When the vehicle is to the right of the path (cte > 0) the CTE term
    subtracts from the heading error, producing a left correction, and
    vice versa.

    Args:
        heading_err_deg: wrap180(path_bearing - current_heading).
            Positive = current heading is CCW of path (right turn needed).
        cte_m: Signed cross-track error from cross_track_error().
            Positive = vehicle is to the RIGHT of the path.
        velocity_mps: Current forward speed.
        k_cte: Stanley gain (rad·(m/s)/m).  Default 0.6.
        v_floor: Minimum speed used in the denominator (prevents ÷0 at standstill).
        max_steer_deg: Output is clipped to ±this value.
        dead_band_m: CTE magnitudes below this are zeroed (suppresses GPS jitter).
    """
    if abs(cte_m) < dead_band_m:
        cte_m = 0.0
    v_eff = max(v_floor, velocity_mps)
    cte_correction = math.degrees(math.atan2(k_cte * cte_m, v_eff))
    steer = heading_err_deg - cte_correction
    return max(-max_steer_deg, min(max_steer_deg, steer))
