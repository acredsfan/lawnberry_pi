import pytest
import httpx

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_maps_api_key_management_and_bypass():
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Read defaults
        resp = await client.get("/api/v2/settings/maps")
        assert resp.status_code == 200
        cfg = resp.json()
        assert cfg["provider"] in {"google", "osm"}
        assert "bypass_external" in cfg

        # Toggle to OSM
        put1 = await client.put("/api/v2/settings/maps", json={"provider": "osm"})
        assert put1.status_code == 200
        body1 = put1.json()
        assert body1["provider"] == "osm"

        # Set Google with a dummy key
        put2 = await client.put("/api/v2/settings/maps", json={"provider": "google", "api_key": "dummy"})
        assert put2.status_code == 200
        body2 = put2.json()
        assert body2["provider"] == "google"
        assert body2["api_key"] == "dummy"

        # Enable bypass mode
        put3 = await client.put("/api/v2/settings/maps", json={"bypass_external": True})
        assert put3.status_code == 200
        body3 = put3.json()
        assert body3["bypass_external"] is True

        # Validation failure on bad provider
        bad = await client.put("/api/v2/settings/maps", json={"provider": "invalid"})
        assert bad.status_code == 422
