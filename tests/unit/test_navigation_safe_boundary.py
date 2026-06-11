from __future__ import annotations

import json

from backend.src.services.boundary_paths import MOWING_BOUNDARY_SAFE, boundary_file


def test_navigation_prefers_generated_safe_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("SIM_MODE", "1")
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    from backend.src.services.navigation_service import NavigationService

    NavigationService._instance = None
    nav = NavigationService()
    safe_path = boundary_file(MOWING_BOUNDARY_SAFE)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(
        json.dumps(
            {
                "buffer_meters": 0.75,
                "coordinates": [
                    {"latitude": 40.0, "longitude": -75.0},
                    {"latitude": 40.0001, "longitude": -75.0},
                    {"latitude": 40.0001, "longitude": -74.9999},
                    {"latitude": 40.0, "longitude": -74.9999},
                ],
            }
        ),
        encoding="utf-8",
    )

    nav._load_boundaries_from_zones()

    assert len(nav.navigation_state.safety_boundaries) == 1
    assert nav.navigation_state.safety_boundaries[0][0].latitude == 40.0
    NavigationService._instance = None
