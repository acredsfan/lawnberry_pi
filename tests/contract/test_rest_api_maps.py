"""Contract tests for map configuration endpoints."""

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


def _sample_zone(zone_id: str, zone_type: str, coordinates):
    return {
        "zone_id": zone_id,
        "zone_type": zone_type,
        "geometry": {
            "type": "Polygon" if zone_type in {"boundary", "exclusion"} else "Point",
            "coordinates": coordinates,
        },
        "priority": 1,
        "color": "#00FF00",
        "last_modified": "2025-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_get_map_configuration_exposes_envelope_with_fallback_status():
    """GET /api/v2/map/configuration should surface zones, provider, and fallback metadata."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/api/v2/map/configuration")

        assert response.status_code == 200, response.text
        payload = response.json()

        assert isinstance(payload.get("zones"), list)
        assert payload.get("provider") in {"google-maps", "osm"}
        assert payload.get("updated_at")
        assert payload.get("updated_by")

        fallback = payload.get("fallback")
        assert isinstance(fallback, dict), "Fallback metadata missing"
        assert {"active", "reason", "provider"}.issubset(fallback.keys())
        assert fallback.get("provider") in {"google-maps", "osm"}

        if payload["zones"]:
            zone = payload["zones"][0]
            for field in ("zone_id", "zone_type", "geometry", "last_modified"):
                assert field in zone


@pytest.mark.asyncio
async def test_put_map_configuration_persists_zones_and_returns_timestamp():
    """PUT /api/v2/map/configuration should accept envelope and confirm persistence."""

    envelope = {
        "zones": [
            _sample_zone(
                "home",
                "home",
                [12.34, 56.78],
            ),
            _sample_zone(
                "boundary-1",
                "boundary",
                [
                    [
                        [12.34, 56.78],
                        [12.35, 56.78],
                        [12.35, 56.79],
                        [12.34, 56.79],
                        [12.34, 56.78],
                    ]
                ],
            ),
        ],
        "provider": "google-maps",
        "updated_by": "contract-test",
        "updated_at": "2025-01-01T00:00:00Z",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        put_response = await client.put("/api/v2/map/configuration", json=envelope)

        assert put_response.status_code == 200, put_response.text
        body = put_response.json()
        assert body.get("status") == "accepted"
        assert body.get("updated_at"), "Updated timestamp missing"

        get_response = await client.get("/api/v2/map/configuration")
        assert get_response.status_code == 200
        retrieved = get_response.json()
        assert any(zone["zone_id"] == "boundary-1" for zone in retrieved.get("zones", []))


@pytest.mark.asyncio
async def test_put_map_configuration_rejects_overlapping_polygons():
    """Overlapping boundary polygons should be rejected with validation detail."""

    overlapping_envelope = {
        "zones": [
            _sample_zone(
                "boundary-a",
                "boundary",
                [[[0.0, 0.0], [0.1, 0.0], [0.1, 0.1], [0.0, 0.1], [0.0, 0.0]]],
            ),
            _sample_zone(
                "boundary-b",
                "boundary",
                [[[0.05, 0.05], [0.15, 0.05], [0.15, 0.15], [0.05, 0.15], [0.05, 0.05]]],
            ),
        ],
        "provider": "google-maps",
        "updated_by": "contract-test",
        "updated_at": "2025-01-01T00:00:00Z",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.put("/api/v2/map/configuration", json=overlapping_envelope)

        assert response.status_code == 400, response.text
        detail = response.json()
        assert detail.get("error_code") == "GEOMETRY_OVERLAP"
        assert "boundary-a" in detail.get("conflicts", [])


@pytest.mark.asyncio
async def test_get_map_configuration_reports_provider_fallback_reason():
    """Fallback metadata should indicate when Google Maps is unavailable and OSM used."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v2/map/configuration",
            params={"simulate_fallback": "google_maps_unavailable"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload.get("provider") == "osm"
        fallback = payload.get("fallback")
        assert fallback and fallback.get("active") is True
        assert fallback.get("reason") == "GOOGLE_MAPS_UNAVAILABLE"
