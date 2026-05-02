"""Pure localization helper functions.

All functions here are stateless, synchronous, and hardware-free. They can be
tested with plain ``pytest`` without any async machinery or sensor fixtures.

These are extracted from NavigationService to support LocalizationService and
to enable independent unit testing of the mathematical core.
"""
from __future__ import annotations

import math

from ..nav.geoutils import body_offset_to_north_east, offset_lat_lon


def heading_delta(target: float, current: float) -> float:
    """Return the signed shortest angular distance from *current* to *target*.

    Positive = clockwise (CW), negative = counter-clockwise (CCW).
    Result is always in the range (-180, +180].

    This is the same formula as ``NavigationService._heading_delta``.
    """
    return (target - current + 180.0) % 360.0 - 180.0


def wrap_heading(degrees: float) -> float:
    """Normalize any heading to [0, 360)."""
    return degrees % 360.0


def apply_antenna_offset(
    *,
    gps_lat: float,
    gps_lon: float,
    forward_m: float,
    right_m: float,
    heading_deg: float,
) -> tuple[float, float]:
    """Translate a GPS antenna position to the mower's geometric center.

    The GPS antenna is physically mounted at an offset from the robot center.
    Given the antenna's lat/lon and the mower's current heading, this returns
    the lat/lon of the mower's center.

    Args:
        gps_lat: Antenna latitude in decimal degrees.
        gps_lon: Antenna longitude in decimal degrees.
        forward_m: Distance of antenna ahead of center (positive = forward).
        right_m: Distance of antenna to the right of center (positive = right).
        heading_deg: Current mower heading in compass degrees (0=N, 90=E).

    Returns:
        (center_lat, center_lon) in decimal degrees.
    """
    if forward_m == 0.0 and right_m == 0.0:
        return gps_lat, gps_lon

    # Compute antenna position relative to center in north/east world frame
    antenna_north_m, antenna_east_m = body_offset_to_north_east(
        forward_m=forward_m,
        right_m=right_m,
        heading_degrees=heading_deg,
    )
    # Center = antenna - antenna_offset
    center_lat, center_lon = offset_lat_lon(
        gps_lat,
        gps_lon,
        north_m=-antenna_north_m,
        east_m=-antenna_east_m,
    )
    return center_lat, center_lon


def resolve_gps_cog_from_inputs(
    *,
    receiver_heading: float | None,
    receiver_speed: float | None,
    derived_cog: float | None,
    derived_speed: float | None,
    speed_threshold: float,
) -> tuple[float | None, float | None, str | None]:
    """Select the best available GPS course-over-ground from pre-computed inputs.

    Preference order:
      1. Receiver-reported heading when ``receiver_speed >= speed_threshold``.
      2. Position-delta-derived COG when available and above threshold.
      3. None when neither is usable.

    This is the decision logic extracted from
    ``NavigationService._resolve_gps_course_over_ground``. The state mutation
    (updating ``_last_gps_track_position`` and ``_last_gps_track_time``) and
    the coordinate-delta calculation remain in ``LocalizationService`` where
    the position history is stored.

    Args:
        receiver_heading: Heading from GPS receiver (degrees), or None.
        receiver_speed: Speed from GPS receiver (m/s), or None.
        derived_cog: Bearing derived from sequential position deltas, or None.
        derived_speed: Speed derived from position deltas (m/s), or None.
        speed_threshold: Minimum speed (m/s) required to accept a COG reading.

    Returns:
        (cog_degrees, speed_mps, source_label) where source is
        ``"receiver"``, ``"position_delta"``, or ``None``.
    """
    if isinstance(receiver_heading, (int, float)):
        speed = float(receiver_speed) if isinstance(receiver_speed, (int, float)) else None
        if speed is not None and speed >= speed_threshold:
            return float(receiver_heading) % 360.0, speed, "receiver"

    if derived_cog is not None:
        return derived_cog, derived_speed, "position_delta"

    return None, None, None


__all__ = [
    "apply_antenna_offset",
    "heading_delta",
    "resolve_gps_cog_from_inputs",
    "wrap_heading",
]
