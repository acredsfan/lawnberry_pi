from __future__ import annotations

"""Simple coverage path planner for lawn mowing (angle=0 only).

Generates parallel scanlines across the boundary polygon and subtracts
exclusion polygons. Returns a serpentine polyline path for visualization
or basic movement testing.

No heavy geometry deps; uses horizontal line intersection against polygon
edges and interval subtraction to avoid holes.
"""

from typing import Iterable, List, Tuple

from .geoutils import haversine_m


LatLng = Tuple[float, float]
Interval = Tuple[float, float]


def _horizontal_intersections(
    polygon: Iterable[LatLng], y: float
) -> List[float]:
    """Compute longitudes where a horizontal scanline at latitude y intersects the polygon.

    Uses half-open edge inclusion to avoid double counting at vertices.
    """
    pts = list(polygon)
    n = len(pts)
    xs: List[float] = []
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


def _intervals_from_intersections(xs: List[float]) -> List[Interval]:
    """Pair sorted intersections into inside intervals along scanline."""
    intervals: List[Interval] = []
    for i in range(0, len(xs) - 1, 2):
        a, b = xs[i], xs[i + 1]
        if b > a:
            intervals.append((a, b))
    return intervals


def _subtract_intervals(source: List[Interval], holes: List[List[Interval]]) -> List[Interval]:
    """Subtract hole intervals from source boundary intervals (1D on scanline).

    Args:
        source: list of non-overlapping [a,b] with a<b
        holes: list of lists of non-overlapping [a,b] intervals to subtract
    Returns:
        list of non-overlapping intervals with holes removed
    """
    result = source[:]
    for hole_list in holes:
        new_result: List[Interval] = []
        for (a, b) in result:
            cur: List[Interval] = [(a, b)]
            for (h1, h2) in hole_list:
                tmp: List[Interval] = []
                for (s1, s2) in cur:
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
        merged: List[Interval] = []
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


def plan_coverage(
    boundary: List[LatLng],
    exclusion_polys: List[List[LatLng]] | None = None,
    spacing_m: float = 0.6,
    angle_deg: float = 0.0,
    max_rows: int = 2000,
) -> Tuple[List[LatLng], int, float]:
    """Compute a serpentine coverage path across boundary with optional holes.

    Currently supports angle=0 only (east-west passes).
    Returns (path_points, row_count, length_m).
    """
    if not boundary or len(boundary) < 3:
        return ([], 0, 0.0)
    if abs(angle_deg) > 1e-6:
        # Not implemented: only support 0 degrees for now
        return ([], 0, 0.0)

    ys = [p[0] for p in boundary]
    xs = [p[1] for p in boundary]
    y_min, y_max = min(ys), max(ys)
    x_min, x_max = min(xs), max(xs)

    # Convert spacing (m) to degrees latitude (approx 111320 m per deg)
    if spacing_m <= 0:
        spacing_m = 0.6
    dy = spacing_m / 111320.0
    if dy <= 0:
        dy = 0.000005

    path: List[LatLng] = []
    row_idx = 0
    length_m = 0.0

    y = y_min
    while y <= y_max + 1e-12 and row_idx < max_rows:
        # Boundary intersections
        bxs = _horizontal_intersections(boundary, y)
        b_intervals = _intervals_from_intersections(bxs)

        # Subtract exclusion intervals
        hole_intervals: List[List[Interval]] = []
        if exclusion_polys:
            for hole in exclusion_polys:
                hxs = _horizontal_intersections(hole, y)
                hole_intervals.append(_intervals_from_intersections(hxs))

        intervals = _subtract_intervals(b_intervals, hole_intervals) if hole_intervals else b_intervals
        # Traverse intervals in serpentine order
        if row_idx % 2 == 0:
            # left -> right per interval order
            for (xa, xb) in intervals:
                a = (y, xa)
                b = (y, xb)
                # Add points
                if not path or path[-1] != a:
                    path.append(a)
                path.append(b)
                length_m += haversine_m(a[0], a[1], b[0], b[1])
        else:
            # right -> left reverse intervals
            for (xa, xb) in reversed(intervals):
                a = (y, xb)
                b = (y, xa)
                if not path or path[-1] != a:
                    path.append(a)
                path.append(b)
                length_m += haversine_m(a[0], a[1], b[0], b[1])

        row_idx += 1
        y += dy

    return (path, row_idx, length_m)
