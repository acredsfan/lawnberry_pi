import math
import pytest


@pytest.mark.asyncio
async def test_generate_parallel_line_pattern_basic():
    """Contract: Generate parallel-line coverage pattern with width/overlap.

    Simple rectangular geofence around a small area near (37.0, -122.0).
    """
    from backend.src.scheduler.coverage_generator import generate_parallel_lines

    geofence = [
        (37.0005, -122.0005),
        (37.0005, -121.9995),
        (36.9995, -121.9995),
        (36.9995, -122.0005),
    ]

    cutting_width_m = 0.4
    overlap_m = 0.04

    lines = generate_parallel_lines(
        geofence_vertices=geofence,
        cutting_width_m=cutting_width_m,
        overlap_m=overlap_m,
        heading_degrees=0.0,  # North-South lines
    )

    # Expect at least a few lines to cover the ~111m by ~111m square (scaled down area)
    assert isinstance(lines, list)
    assert len(lines) >= 3

    # All waypoints must be within geofence bounding box (coarse check)
    lats = [lat for lat, _ in geofence]
    lons = [lon for _, lon in geofence]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    for (a, b) in lines:
        for lat, lon in (a, b):
            assert min_lat <= lat <= max_lat
            assert min_lon <= lon <= max_lon

    # Adjacent lines should be roughly spaced by width-overlap in meters
    # Convert degree delta to meters using simple approximation around latitude
    def deg_to_m(dlat, dlon, lat0=37.0):
        m_per_deg_lat = 111_320.0
        m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
        return abs(dlat) * m_per_deg_lat + abs(dlon) * m_per_deg_lon

    spacings = []
    for i in range(1, len(lines)):
        (a1, b1) = lines[i - 1]
        (a2, b2) = lines[i]
        # Use midpoints of the two lines to compute spacing
        m1 = ((a1[0] + b1[0]) / 2.0, (a1[1] + b1[1]) / 2.0)
        m2 = ((a2[0] + b2[0]) / 2.0, (a2[1] + b2[1]) / 2.0)
        spacings.append(deg_to_m(m2[0] - m1[0], m2[1] - m1[1]))

    target_spacing = cutting_width_m - overlap_m
    # Allow some tolerance due to degree rounding
    assert any(abs(s - target_spacing) < 0.15 for s in spacings)
