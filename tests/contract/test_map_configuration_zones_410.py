"""Contract test: PUT /map/configuration returns 410 when body contains zones."""

from __future__ import annotations

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_put_map_configuration_with_zones_returns_410():
    """PUT /api/v2/map/configuration with zones key must return 410 Gone."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.put(
            "/api/v2/map/configuration",
            json={"zones": [{"id": "z1", "polygon": []}]},
        )
        assert resp.status_code == 410, resp.text


@pytest.mark.asyncio
async def test_put_map_configuration_with_boundaries_returns_410():
    """PUT /api/v2/map/configuration with boundaries key must return 410 Gone."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.put(
            "/api/v2/map/configuration",
            json={"boundaries": [{"coordinates": [[0, 0], [1, 0], [1, 1]]}]},
        )
        assert resp.status_code == 410, resp.text


@pytest.mark.asyncio
async def test_put_map_configuration_with_exclusion_zones_returns_410():
    """PUT /api/v2/map/configuration with exclusion_zones key must return 410 Gone."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.put(
            "/api/v2/map/configuration",
            json={"exclusion_zones": []},
        )
        assert resp.status_code == 410, resp.text


@pytest.mark.asyncio
async def test_put_map_configuration_without_zones_returns_200():
    """PUT /api/v2/map/configuration without spatial keys must succeed."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.put(
            "/api/v2/map/configuration",
            json={"provider": "osm"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body.get("status") == "accepted"


@pytest.mark.asyncio
async def test_put_map_configuration_410_detail_mentions_zones_endpoint():
    """410 response detail should guide callers to use /api/v2/map/zones/{id}."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.put(
            "/api/v2/map/configuration",
            json={"zones": []},
        )
        assert resp.status_code == 410, resp.text
        detail = resp.json().get("detail", "")
        assert "zones" in detail.lower() or "map/zones" in detail.lower()
