"""Contract tests for the navigation coverage plan endpoint."""

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


def _boundary_zone() -> dict:
    return {
        "zone_id": "boundary-1",
        "zone_type": "boundary",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [-74.0060, 40.7128],
                    [-74.0056, 40.7128],
                    [-74.0056, 40.7132],
                    [-74.0060, 40.7132],
                    [-74.0060, 40.7128],
                ]
            ],
        },
    }


@pytest.mark.asyncio
async def test_get_coverage_plan_returns_linestring_for_saved_boundary():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        put_response = await client.put(
            "/api/v2/map/configuration",
            params={"config_id": "coverage-test"},
            json={
                "zones": [_boundary_zone()],
                "provider": "osm",
                "updated_by": "coverage-contract",
            },
        )
        assert put_response.status_code == 200, put_response.text

        response = await client.get(
            "/api/v2/nav/coverage-plan",
            params={"config_id": "coverage-test", "spacing_m": 0.6},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        geometry = payload.get("plan", {}).get("geometry", {})
        properties = payload.get("plan", {}).get("properties", {})

        assert geometry.get("type") == "LineString"
        assert len(geometry.get("coordinates", [])) >= 2
        assert properties.get("config_id") == "coverage-test"
        assert properties.get("row_count", 0) > 0


@pytest.mark.asyncio
async def test_get_coverage_plan_requires_boundary_zone():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        put_response = await client.put(
            "/api/v2/map/configuration",
            params={"config_id": "coverage-empty"},
            json={
                "zones": [],
                "provider": "osm",
                "updated_by": "coverage-contract",
            },
        )
        assert put_response.status_code == 200, put_response.text

        response = await client.get(
            "/api/v2/nav/coverage-plan",
            params={"config_id": "coverage-empty"},
        )

        assert response.status_code == 404, response.text
        assert "Boundary zone" in response.json().get("detail", "")