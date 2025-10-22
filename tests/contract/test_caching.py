import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_etag_and_if_none_match_on_map_zones():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial GET
        r1 = await client.get("/api/v2/map/zones")
        assert r1.status_code == 200
        etag = r1.headers.get("etag")
        assert etag
        # Conditional GET with If-None-Match
        r2 = await client.get("/api/v2/map/zones", headers={"If-None-Match": etag})
        assert r2.status_code == 304

@pytest.mark.asyncio
async def test_last_modified_and_if_modified_since_on_settings():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Initial GET
        r1 = await client.get("/api/v2/settings/system")
        assert r1.status_code == 200
        last_mod = r1.headers.get("last-modified")
        assert last_mod
        # Conditional GET with If-Modified-Since
        r2 = await client.get("/api/v2/settings/system", headers={"If-Modified-Since": last_mod})
        assert r2.status_code == 304

@pytest.mark.asyncio
async def test_etag_changes_after_update_locations():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/api/v2/map/locations")
        assert r1.status_code == 200
        etag1 = r1.headers.get("etag")
        assert etag1
        # Update map locations
        payload = {"home": {"latitude": 1.0, "longitude": 2.0}, "am_sun": None, "pm_sun": None}
        r_put = await client.put("/api/v2/map/locations", json=payload)
        assert r_put.status_code == 200
        # Fetch again and compare ETag
        r2 = await client.get("/api/v2/map/locations")
        etag2 = r2.headers.get("etag")
        assert etag2 and etag2 != etag1
