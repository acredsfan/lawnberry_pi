from __future__ import annotations

import json

import pytest

from backend.src.services.geofence_buffer import (
    DEFAULT_SAFE_BOUNDARY_BUFFER_METERS,
    create_safe_boundary,
    default_buffer_meters,
    save_safe_boundary,
)
from backend.src.services.parcel_boundary import (
    clear_imported_property_boundary,
    get_imported_property_boundary,
    load_geojson_boundary,
    load_kml_boundary,
    save_imported_property_boundary,
)


def _square(lat: float = 40.0, lng: float = -75.0, size: float = 0.0002):
    return [
        {"latitude": lat, "longitude": lng},
        {"latitude": lat + size, "longitude": lng},
        {"latitude": lat + size, "longitude": lng + size},
        {"latitude": lat, "longitude": lng + size},
    ]


def test_geojson_import_normalizes_lng_lat_ring():
    payload = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-75.0, 40.0],
                [-75.0, 40.0002],
                [-74.9998, 40.0002],
                [-74.9998, 40.0],
                [-75.0, 40.0],
            ]],
        },
        "properties": {},
    }

    points = load_geojson_boundary(json.dumps(payload))

    assert points[0] == {"latitude": 40.0, "longitude": -75.0}
    assert len(points) == 4


def test_kml_import_normalizes_coordinates():
    kml = """
    <kml><Document><Placemark><Polygon><outerBoundaryIs><LinearRing>
    <coordinates>-75.0,40.0,0 -75.0,40.0002,0 -74.9998,40.0002,0 -75.0,40.0,0</coordinates>
    </LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>
    """

    points = load_kml_boundary(kml)

    assert len(points) == 3
    assert points[1]["latitude"] == pytest.approx(40.0002)


def test_imported_property_boundary_is_helper_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))

    saved = save_imported_property_boundary(_square())

    assert saved["helper_only"] is True
    assert saved["confidence"] == "helper_only"
    assert get_imported_property_boundary()["coordinates"] == saved["coordinates"]
    clear_imported_property_boundary()
    assert get_imported_property_boundary() is None


def test_safe_boundary_default_is_five_centimeter_additional_inset(monkeypatch):
    monkeypatch.delenv("SAFE_BOUNDARY_BUFFER_METERS", raising=False)

    assert default_buffer_meters() == DEFAULT_SAFE_BOUNDARY_BUFFER_METERS == 0.05


def test_safe_boundary_uses_override_and_shrinks_polygon(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    points = _square(size=0.001)

    safe = save_safe_boundary(points, buffer_meters=0.25)

    assert safe["buffer_meters"] == 0.25
    assert len(safe["coordinates"]) >= 3
    assert create_safe_boundary(points, 0.25) == safe["coordinates"]
