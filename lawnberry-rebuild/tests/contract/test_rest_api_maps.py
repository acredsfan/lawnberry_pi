import pytest
import httpx

from backend.src.main import app


@pytest.mark.asyncio
async def test_get_map_zones_returns_list():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/map/zones")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_post_map_zones_accepts_array():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = [
            {
                "id": "front",
                "name": "Front Yard",
                "polygon": [{"latitude": 0, "longitude": 0}],
                "priority": 1,
                "exclusion_zone": False,
            }
        ]
        resp = await client.post("/api/v2/map/zones", json=payload)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_map_locations_returns_object():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/map/locations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)


@pytest.mark.asyncio
async def test_put_map_locations_accepts_object():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "home": None,
            "am_sun": None,
            "pm_sun": None,
        }
        resp = await client.put("/api/v2/map/locations", json=payload)
        assert resp.status_code == 200
