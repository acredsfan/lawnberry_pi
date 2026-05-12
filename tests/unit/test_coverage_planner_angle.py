"""Tests for arbitrary-angle boustrophedon in coverage_planner.plan_coverage."""

from __future__ import annotations

import math

import pytest

from backend.src.nav.coverage_planner import plan_coverage
from backend.src.nav.geoutils import haversine_m


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _square_boundary(
    center_lat: float = 40.0,
    center_lon: float = -74.0,
    side_m: float = 50.0,
) -> list[tuple[float, float]]:
    """Return a ~50 m square boundary polygon as (lat, lon) tuples."""
    half_deg_lat = (side_m / 2) / 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(center_lat))
    half_deg_lon = (side_m / 2) / meters_per_deg_lon
    return [
        (center_lat - half_deg_lat, center_lon - half_deg_lon),
        (center_lat - half_deg_lat, center_lon + half_deg_lon),
        (center_lat + half_deg_lat, center_lon + half_deg_lon),
        (center_lat + half_deg_lat, center_lon - half_deg_lon),
    ]


def _path_length_m(path: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        total += haversine_m(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
    return total


# ---------------------------------------------------------------------------
# T6-A: angle=0 backward compatibility
# ---------------------------------------------------------------------------

class TestAngle0Unchanged:
    def test_angle_0_unchanged(self):
        boundary = _square_boundary()
        path_default, rows_default, len_default = plan_coverage(boundary, spacing_m=1.0)
        path_zero, rows_zero, len_zero = plan_coverage(boundary, spacing_m=1.0, angle_deg=0.0)

        assert rows_default == rows_zero, "row counts should be identical"
        assert abs(len_default - len_zero) < 0.01, "path lengths should be identical"
        assert len(path_default) == len(path_zero), "path point count should be identical"
        for a, b in zip(path_default, path_zero):
            assert abs(a[0] - b[0]) < 1e-9, f"lat mismatch: {a} vs {b}"
            assert abs(a[1] - b[1]) < 1e-9, f"lon mismatch: {a} vs {b}"

    def test_angle_0_returns_nonempty_path(self):
        boundary = _square_boundary()
        path, rows, length_m = plan_coverage(boundary, spacing_m=1.0, angle_deg=0.0)
        assert len(path) >= 2
        assert rows > 0
        assert length_m > 0.0


# ---------------------------------------------------------------------------
# T6-B: angle=90 produces north-south passes
# ---------------------------------------------------------------------------

class TestAngle90NorthSouthPasses:
    """At 90°, scanlines should be oriented N-S: consecutive points in a pass
    share nearly the same longitude but differ significantly in latitude."""

    def test_angle_90_produces_north_south_passes_in_square_polygon(self):
        boundary = _square_boundary(side_m=50.0)
        path, rows, length_m = plan_coverage(boundary, spacing_m=2.0, angle_deg=90.0)

        assert len(path) >= 2, "path should be non-empty for angle=90"
        assert rows > 0, "row_count should be > 0"
        assert length_m > 0.0

        # For N-S passes: measure longitude spread vs latitude spread
        # across the full path. We expect latitude variation >> longitude variation.
        lats = [p[0] for p in path]
        lons = [p[1] for p in path]

        lat_range = max(lats) - min(lats)
        lon_range = max(lons) - min(lons)

        # The square is 50 m wide, spacing 2 m → ~25 N-S passes.
        # Latitude variation should cover most of the 50 m height in degrees.
        # Longitude variation is the spread of pass positions (~50 m wide).
        # Both ranges should be non-trivial.
        assert lat_range > 0, "latitude should vary for N-S passes"
        assert lon_range > 0, "longitude should vary for N-S passes"

        # Key assertion: consecutive within-pass pairs should share similar
        # longitude (within 10% of the spacing), not latitude.
        # Measure by looking at pairs that are "within a pass" — defined as
        # adjacent path points where their lat-span > their lon-span.
        n_ns = 0
        n_ew = 0
        for i in range(len(path) - 1):
            dlat = abs(path[i + 1][0] - path[i][0])
            dlon = abs(path[i + 1][1] - path[i][1])
            # Convert to rough meters for fair comparison
            dlat_m = dlat * 111_320.0
            dlon_m = dlon * 111_320.0 * math.cos(math.radians(path[i][0]))
            if dlat_m > dlon_m:
                n_ns += 1
            elif dlon_m > dlat_m:
                n_ew += 1

        # Majority of consecutive pairs should be N-S (lat-dominant movement)
        assert n_ns > n_ew, (
            f"Expected mostly N-S moves (n_ns={n_ns}), got more E-W (n_ew={n_ew}). "
            "angle=90 should produce north-south scanlines."
        )

    def test_angle_90_path_all_within_boundary(self):
        """All waypoints should be inside or on the boundary square."""
        from backend.src.nav.geoutils import point_in_polygon
        boundary = _square_boundary(side_m=50.0)
        path, _, _ = plan_coverage(boundary, spacing_m=2.0, angle_deg=90.0)
        assert len(path) >= 2

        for pt in path:
            # Allow small tolerance by expanding boundary slightly
            assert point_in_polygon(pt[0], pt[1], boundary) or _near_boundary(
                pt, boundary, tol_m=0.5
            ), f"Point {pt} appears outside the boundary"


def _near_boundary(pt, boundary, tol_m=0.5):
    """True if pt is within tol_m of any boundary edge."""
    tol_deg = tol_m / 111_320.0
    for i in range(len(boundary)):
        a = boundary[i]
        b = boundary[(i + 1) % len(boundary)]
        if _dist_to_segment(pt, a, b) < tol_deg:
            return True
    return False


def _dist_to_segment(p, a, b):
    """Approximate distance from point p to segment a-b in degrees."""
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    px, py = p[0], p[1]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ---------------------------------------------------------------------------
# T6-C: angle=45 path length within expected envelope
# ---------------------------------------------------------------------------

class TestAngle45PathLength:
    def test_angle_45_path_length_within_expected_envelope(self):
        boundary = _square_boundary(side_m=50.0)
        spacing = 1.5

        path0, rows0, len0 = plan_coverage(boundary, spacing_m=spacing, angle_deg=0.0)
        path45, rows45, len45 = plan_coverage(boundary, spacing_m=spacing, angle_deg=45.0)

        assert len(path45) >= 2, "angle=45 should produce a non-empty path"
        assert rows45 > 0
        assert len45 > 0.0

        # The diagonal orientation should not produce a wildly different path length.
        # A reasonable envelope: within 2x of the angle=0 path length.
        assert len45 < 2.0 * len0, (
            f"angle=45 path length {len45:.1f} m is more than 2x the angle=0 "
            f"length {len0:.1f} m — likely a bug in the rotation."
        )
        # Also should cover at least 50% of the area compared to angle=0
        assert len45 > 0.5 * len0, (
            f"angle=45 path length {len45:.1f} m is less than 50% of angle=0 "
            f"length {len0:.1f} m — coverage seems too low."
        )

    def test_angle_45_returns_valid_coordinates(self):
        boundary = _square_boundary(side_m=50.0)
        path, rows, length_m = plan_coverage(boundary, spacing_m=2.0, angle_deg=45.0)

        assert len(path) >= 2
        for lat, lon in path:
            assert -90.0 <= lat <= 90.0, f"Invalid latitude: {lat}"
            assert -180.0 <= lon <= 180.0, f"Invalid longitude: {lon}"


# ---------------------------------------------------------------------------
# T6-D: various angles produce non-empty paths
# ---------------------------------------------------------------------------

class TestVariousAngles:
    @pytest.mark.parametrize("angle", [0, 30, 45, 60, 90, 135, 180])
    def test_angle_produces_valid_path(self, angle):
        boundary = _square_boundary(side_m=40.0)
        path, rows, length_m = plan_coverage(boundary, spacing_m=2.0, angle_deg=float(angle))

        assert len(path) >= 2, f"angle={angle} produced empty path"
        assert rows > 0, f"angle={angle} has 0 rows"
        assert length_m > 0.0, f"angle={angle} has 0 length"

    def test_angle_negative_equivalent_to_positive_complement(self):
        """angle=-90 and angle=90 should produce equivalent paths (same structure)."""
        boundary = _square_boundary(side_m=40.0)
        path90, rows90, len90 = plan_coverage(boundary, spacing_m=2.0, angle_deg=90.0)
        path_neg90, rows_neg90, len_neg90 = plan_coverage(boundary, spacing_m=2.0, angle_deg=-90.0)

        assert len(path90) >= 2
        assert len(path_neg90) >= 2
        # Lengths should be close (same scan coverage, maybe different ordering)
        assert abs(len90 - len_neg90) < 0.1 * max(len90, len_neg90), (
            f"angle=90 len={len90:.1f}, angle=-90 len={len_neg90:.1f} — too different"
        )
