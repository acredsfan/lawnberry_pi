from __future__ import annotations

"""Simple coverage path planner for lawn mowing (arbitrary angle).

Generates parallel scanlines across the boundary polygon and subtracts
exclusion polygons. Returns a serpentine polyline path for visualization
or basic movement testing.

No heavy geometry deps; uses horizontal line intersection against polygon
edges and interval subtraction to avoid holes.

Angle support is implemented by converting all coordinates to a local ENU
(East-North-Up) Cartesian frame, rotating them so that the desired pass
direction aligns with the scanline axis (east), running the existing
horizontal scanline algorithm in ENU space, and then un-rotating and
converting back to lat/lng.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from .geoutils import enu_to_latlon, haversine_m, latlon_to_enu, rotate_enu

LatLng = tuple[float, float]
Interval = tuple[float, float]


@dataclass(frozen=True)
class CoverageSegment:
    """One blade-on scanline segment; connectors are planned separately."""

    start: LatLng
    end: LatLng


def _horizontal_intersections(polygon: Iterable[LatLng], y: float) -> list[float]:
    """Compute longitudes where a horizontal scanline at latitude y intersects the polygon.

    Uses half-open edge inclusion to avoid double counting at vertices.
    """
    pts = list(polygon)
    n = len(pts)
    xs: list[float] = []
    for i in range(n):
        (y1, x1) = pts[i]
        (y2, x2) = pts[(i + 1) % n]
        # Skip horizontal edges
        if y1 == y2:
            continue
        # Check if scanline crosses the edge in half-open sense [min, max)
        ymin = min(y1, y2)
        ymax = max(y1, y2)
        if not (y >= ymin and y < ymax):
            continue
        t = (y - y1) / (y2 - y1)
        x = x1 + t * (x2 - x1)
        xs.append(x)
    xs.sort()
    return xs


def _intervals_from_intersections(xs: list[float]) -> list[Interval]:
    """Pair sorted intersections into inside intervals along scanline."""
    intervals: list[Interval] = []
    for i in range(0, len(xs) - 1, 2):
        a, b = xs[i], xs[i + 1]
        if b > a:
            intervals.append((a, b))
    return intervals


def _subtract_intervals(source: list[Interval], holes: list[list[Interval]]) -> list[Interval]:
    """Subtract hole intervals from source boundary intervals (1D on scanline).

    Args:
        source: list of non-overlapping [a,b] with a<b
        holes: list of lists of non-overlapping [a,b] intervals to subtract
    Returns:
        list of non-overlapping intervals with holes removed
    """
    result = source[:]
    for hole_list in holes:
        new_result: list[Interval] = []
        for a, b in result:
            cur: list[Interval] = [(a, b)]
            for h1, h2 in hole_list:
                tmp: list[Interval] = []
                for s1, s2 in cur:
                    # No overlap
                    if h2 <= s1 or h1 >= s2:
                        tmp.append((s1, s2))
                    else:
                        # Cut out the overlapping part
                        if h1 > s1:
                            tmp.append((s1, min(h1, s2)))
                        if h2 < s2:
                            tmp.append((max(h2, s1), s2))
                cur = [(x1, x2) for (x1, x2) in tmp if x2 > x1]
            new_result.extend(cur)
        # Normalize/merge adjacent small gaps
        new_result.sort()
        merged: list[Interval] = []
        for seg in new_result:
            if not merged:
                merged.append(seg)
            else:
                (m1, m2) = merged[-1]
                if abs(seg[0] - m2) < 1e-12:  # touch
                    merged[-1] = (m1, seg[1])
                elif seg[0] > m2:
                    merged.append(seg)
        result = merged
    return result


def _polygon_centroid_latlon(boundary: list[LatLng]) -> LatLng:
    """Return the arithmetic centroid (lat, lon) of a polygon's vertices."""
    lat = sum(p[0] for p in boundary) / len(boundary)
    lon = sum(p[1] for p in boundary) / len(boundary)
    return lat, lon


def _run_scanline(
    boundary_enu: list[tuple[float, float]],
    exclusion_enus: list[list[tuple[float, float]]],
    spacing_m: float,
    max_rows: int,
) -> tuple[list[tuple[float, float]], int, float]:
    """Run the horizontal scanline algorithm in ENU (meters) space.

    Parameters are in ENU coordinates where axis-0 is "north" (y) and
    axis-1 is "east" (x).  Points here are represented as (y_m, x_m)
    — the same layout as (lat, lon) in the original algorithm — so all
    helper functions (_horizontal_intersections, etc.) work unchanged.

    Returns (enu_path, row_count, length_m).
    """
    ys = [p[0] for p in boundary_enu]
    y_min, y_max = min(ys), max(ys)

    dy = spacing_m
    if dy <= 0:
        dy = 0.6

    path: list[tuple[float, float]] = []
    row_idx = 0
    length_m = 0.0

    y = y_min
    while y <= y_max + 1e-9 and row_idx < max_rows:
        bxs = _horizontal_intersections(boundary_enu, y)
        b_intervals = _intervals_from_intersections(bxs)

        hole_intervals: list[list[Interval]] = []
        for hole in exclusion_enus:
            hxs = _horizontal_intersections(hole, y)
            hole_intervals.append(_intervals_from_intersections(hxs))

        intervals = (
            _subtract_intervals(b_intervals, hole_intervals) if hole_intervals else b_intervals
        )

        if row_idx % 2 == 0:
            for xa, xb in intervals:
                a = (y, xa)
                b = (y, xb)
                if not path or path[-1] != a:
                    path.append(a)
                path.append(b)
                # In ENU space, distance is just Euclidean (meters)
                length_m += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        else:
            for xa, xb in reversed(intervals):
                a = (y, xb)
                b = (y, xa)
                if not path or path[-1] != a:
                    path.append(a)
                path.append(b)
                length_m += ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5

        row_idx += 1
        y += dy

    return path, row_idx, length_m


def plan_coverage(
    boundary: list[LatLng],
    exclusion_polys: list[list[LatLng]] | None = None,
    spacing_m: float = 0.6,
    angle_deg: float = 0.0,
    max_rows: int = 2000,
) -> tuple[list[LatLng], int, float]:
    """Compute a serpentine coverage path across boundary with optional holes.

    Supports arbitrary ``angle_deg`` (east-west passes = 0°, north-south = 90°,
    and any diagonal).  The algorithm converts coordinates to a local ENU
    Cartesian frame, rotates to align scanlines with the desired direction,
    runs the horizontal scanline, then un-rotates and converts back to lat/lng.

    Returns (path_points, row_count, length_m).
    """
    if not boundary or len(boundary) < 3:
        return ([], 0, 0.0)

    if spacing_m <= 0:
        spacing_m = 0.6

    # --- fast path for angle=0: use the original lat/lng based algorithm ---
    if abs(angle_deg) < 1e-6:
        ys = [p[0] for p in boundary]
        y_min, y_max = min(ys), max(ys)
        dy = spacing_m / 111320.0
        if dy <= 0:
            dy = 0.000005

        path: list[LatLng] = []
        row_idx = 0
        length_m = 0.0
        y = y_min
        while y <= y_max + 1e-12 and row_idx < max_rows:
            bxs = _horizontal_intersections(boundary, y)
            b_intervals = _intervals_from_intersections(bxs)

            hole_intervals: list[list[Interval]] = []
            if exclusion_polys:
                for hole in exclusion_polys:
                    hxs = _horizontal_intersections(hole, y)
                    hole_intervals.append(_intervals_from_intersections(hxs))

            intervals = (
                _subtract_intervals(b_intervals, hole_intervals) if hole_intervals else b_intervals
            )
            if row_idx % 2 == 0:
                for xa, xb in intervals:
                    a = (y, xa)
                    b = (y, xb)
                    if not path or path[-1] != a:
                        path.append(a)
                    path.append(b)
                    length_m += haversine_m(a[0], a[1], b[0], b[1])
            else:
                for xa, xb in reversed(intervals):
                    a = (y, xb)
                    b = (y, xa)
                    if not path or path[-1] != a:
                        path.append(a)
                    path.append(b)
                    length_m += haversine_m(a[0], a[1], b[0], b[1])

            row_idx += 1
            y += dy

        return (path, row_idx, length_m)

    # --- arbitrary angle: ENU + rotation pipeline ---
    origin_lat, origin_lon = _polygon_centroid_latlon(boundary)

    def to_rotated_enu(latlng_poly: list[LatLng], rot_deg: float) -> list[tuple[float, float]]:
        """Convert lat/lon polygon to ENU (meters) then rotate by rot_deg."""
        result: list[tuple[float, float]] = []
        for lat, lon in latlng_poly:
            east_m, north_m = latlon_to_enu(lat, lon, origin_lat, origin_lon)
            # Rotate: positive angle_deg means CW from east in compass terms.
            # We rotate by -angle_deg so scanlines (which scan along "east" in
            # the rotated frame) align with the desired bearing.
            re, rn = rotate_enu(east_m, north_m, rot_deg)
            # Represent as (y, x) = (north, east) so _horizontal_intersections works.
            result.append((rn, re))
        return result

    # Rotate boundary and exclusions by -angle_deg
    boundary_enu = to_rotated_enu(boundary, -angle_deg)
    exclusion_enus = [to_rotated_enu(ep, -angle_deg) for ep in (exclusion_polys or [])]

    enu_path, row_count, length_m = _run_scanline(
        boundary_enu, exclusion_enus, spacing_m, max_rows
    )

    # Un-rotate and convert back to lat/lon
    geo_path: list[LatLng] = []
    for north_m_rot, east_m_rot in enu_path:
        # enu_path stores (north, east) — swap back to (east, north) for rotate
        ue, un = rotate_enu(east_m_rot, north_m_rot, +angle_deg)
        lat, lon = enu_to_latlon(ue, un, origin_lat, origin_lon)
        geo_path.append((lat, lon))

    return (geo_path, row_count, length_m)


def plan_coverage_segments(
    boundary: list[LatLng],
    exclusion_polys: list[list[LatLng]] | None = None,
    *,
    spacing_m: float = 0.6,
    angle_deg: float = 0.0,
    clearance_m: float = 0.0,
    max_rows: int = 2000,
) -> tuple[list[CoverageSegment], int, float]:
    """Return footprint-eroded mow segments without inventing unsafe connectors.

    The free-space polygon is projected to metres, eroded by ``clearance_m``
    (which also expands holes), and then scan-converted. Each returned segment
    is independently safe for mowing; callers must plan blade-off connectors.
    """
    if len(boundary) < 3:
        return [], 0, 0.0

    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    origin_lat, origin_lon = _polygon_centroid_latlon(boundary)

    def to_rotated(poly: list[LatLng]) -> list[tuple[float, float]]:
        converted: list[tuple[float, float]] = []
        for lat, lon in poly:
            east_m, north_m = latlon_to_enu(lat, lon, origin_lat, origin_lon)
            rotated_east, rotated_north = rotate_enu(east_m, north_m, -angle_deg)
            converted.append((rotated_north, rotated_east))
        return converted

    outer = Polygon(to_rotated(boundary))
    if not outer.is_valid:
        outer = outer.buffer(0)
    holes = []
    for exclusion in exclusion_polys or []:
        if len(exclusion) < 3:
            continue
        polygon = Polygon(to_rotated(exclusion))
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty:
            holes.append(polygon)
    free_space = outer.difference(unary_union(holes)) if holes else outer
    if clearance_m > 0:
        free_space = free_space.buffer(-float(clearance_m), join_style=2)
    if free_space.is_empty:
        return [], 0, 0.0

    if isinstance(free_space, Polygon):
        polygons = [free_space]
    else:
        polygons = [
            geometry
            for geometry in getattr(free_space, "geoms", ())
            if isinstance(geometry, Polygon) and not geometry.is_empty
        ]
    if not polygons:
        return [], 0, 0.0
    raw_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    row_count = 0
    direction_forward = True
    spacing = spacing_m if spacing_m > 0 else 0.6

    for polygon in sorted(polygons, key=lambda item: (-item.area, item.bounds)):
        exterior = [(float(x), float(y)) for x, y in polygon.exterior.coords[:-1]]
        interiors = [
            [(float(x), float(y)) for x, y in ring.coords[:-1]]
            for ring in polygon.interiors
        ]
        ys = [point[0] for point in exterior]
        y = min(ys)
        y_max = max(ys)
        while y <= y_max + 1e-9 and row_count < max_rows:
            source = _intervals_from_intersections(_horizontal_intersections(exterior, y))
            hole_intervals = [
                _intervals_from_intersections(_horizontal_intersections(interior, y))
                for interior in interiors
            ]
            intervals = _subtract_intervals(source, hole_intervals) if hole_intervals else source
            ordered = intervals if direction_forward else list(reversed(intervals))
            for start_x, end_x in ordered:
                if direction_forward:
                    raw_segments.append(((y, start_x), (y, end_x)))
                else:
                    raw_segments.append(((y, end_x), (y, start_x)))
            if intervals:
                direction_forward = not direction_forward
            row_count += 1
            y += spacing

    def to_latlng(point: tuple[float, float]) -> LatLng:
        north_rotated, east_rotated = point
        east_m, north_m = rotate_enu(east_rotated, north_rotated, angle_deg)
        return enu_to_latlon(east_m, north_m, origin_lat, origin_lon)

    segments = [CoverageSegment(start=to_latlng(a), end=to_latlng(b)) for a, b in raw_segments]
    mow_length_m = sum(
        haversine_m(segment.start[0], segment.start[1], segment.end[0], segment.end[1])
        for segment in segments
    )
    return segments, row_count, mow_length_m
