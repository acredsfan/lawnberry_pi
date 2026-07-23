from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.src.api import boundary as boundary_api


@pytest.mark.asyncio
async def test_generate_safe_boundary_uses_current_persisted_boundary_zone(monkeypatch):
    coordinates = [
        {"latitude": 40.0, "longitude": -75.0},
        {"latitude": 40.0002, "longitude": -75.0},
        {"latitude": 40.0002, "longitude": -74.9998},
    ]

    class Repository:
        def get_zone(self, zone_id):
            assert zone_id == "confirmed_mowing_boundary"
            return None

        def list_zones(self):
            return [
                {
                    "id": "boundary_1781728519579",
                    "zone_kind": "boundary",
                    "priority": 0,
                    "polygon": coordinates,
                }
            ]

    captured = {}

    def fake_save(points, *, buffer_meters):
        captured["coordinates"] = points
        captured["buffer_meters"] = buffer_meters
        return {"coordinates": points, "buffer_meters": buffer_meters}

    monkeypatch.setattr(boundary_api, "save_safe_boundary", fake_save)

    result = await boundary_api.generate_safe_boundary(
        boundary_api.GenerateSafeRequest(buffer_meters=0.05),
        SimpleNamespace(
            map_repository=Repository(),
            safety_limits=SimpleNamespace(geofence_buffer_meters=0.15),
            navigation=MagicMock(),
        ),
    )

    assert captured == {"coordinates": coordinates, "buffer_meters": 0.05}
    assert result["coordinates"] == coordinates


@pytest.mark.asyncio
async def test_generate_safe_boundary_defaults_to_live_additional_inset(monkeypatch):
    coordinates = [
        {"latitude": 40.0, "longitude": -75.0},
        {"latitude": 40.0002, "longitude": -75.0},
        {"latitude": 40.0002, "longitude": -74.9998},
    ]
    repository = SimpleNamespace(
        get_zone=lambda _zone_id: {"polygon": coordinates},
        list_zones=lambda: [],
    )
    captured = {}

    def fake_save(points, *, buffer_meters):
        captured.update(points=points, buffer_meters=buffer_meters)
        return captured

    monkeypatch.setattr(boundary_api, "save_safe_boundary", fake_save)

    await boundary_api.generate_safe_boundary(
        boundary_api.GenerateSafeRequest(),
        SimpleNamespace(
            map_repository=repository,
            safety_limits=SimpleNamespace(geofence_buffer_meters=0.05),
        ),
    )

    assert captured["buffer_meters"] == 0.05
