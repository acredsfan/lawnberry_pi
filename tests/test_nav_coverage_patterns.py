import pytest

pytest.importorskip("shapely")

from backend.src.nav.coverage_patterns import CoverageConfig, generate_lawnmower
from backend.src.models import Position


def rectangle(lat0=0.0, lon0=0.0, width_m=20.0, height_m=10.0):
    # Build rectangle positions in lat/lon
    lat_step = height_m / 111000.0
    lon_step = width_m / (111000.0)
    return [
        Position(latitude=lat0, longitude=lon0),
        Position(latitude=lat0, longitude=lon0 + lon_step),
        Position(latitude=lat0 + lat_step, longitude=lon0 + lon_step),
        Position(latitude=lat0 + lat_step, longitude=lon0),
    ]


def test_generate_lawnmower_basic():
    boundary = rectangle()
    cfg = CoverageConfig(swath_width_m=1.0, overlap=0.1, heading_deg=0.0)
    wps = generate_lawnmower(boundary, config=cfg)
    assert len(wps) > 0
    # Waypoints alternate along stripes; ensure they lie within lat bounds roughly
    lats = [wp.position.latitude for wp in wps]
    assert min(lats) >= min(p.latitude for p in boundary) - 1e-6
    assert max(lats) <= max(p.latitude for p in boundary) + 1e-6
