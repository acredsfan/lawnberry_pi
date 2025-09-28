import pytest
import httpx
from backend.src.main import app


@pytest.mark.asyncio
async def test_get_settings_system_returns_config():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/settings/system")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        # Check for expected top-level keys
        expected_keys = ["hardware", "operation", "telemetry", "ai", "ui"]
        for key in expected_keys:
            assert key in body


@pytest.mark.asyncio
async def test_put_settings_system_updates_config():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # First get current settings
        get_resp = await client.get("/api/v2/settings/system")
        current_settings = get_resp.json()
        
        # Modify some settings
        updated_settings = current_settings.copy()
        updated_settings["telemetry"]["cadence_hz"] = 8
        updated_settings["operation"]["simulation_mode"] = True
        
        # Update via PUT
        put_resp = await client.put("/api/v2/settings/system", json=updated_settings)
        assert put_resp.status_code == 200
        
        # Verify changes were applied
        verify_resp = await client.get("/api/v2/settings/system")
        verify_body = verify_resp.json()
        assert verify_body["telemetry"]["cadence_hz"] == 8
        assert verify_body["operation"]["simulation_mode"] is True


@pytest.mark.asyncio
async def test_put_settings_system_validates_cadence():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get current settings
        get_resp = await client.get("/api/v2/settings/system")
        settings = get_resp.json()
        
        # Try invalid cadence (out of range)
        settings["telemetry"]["cadence_hz"] = 15  # Should be 1-10
        
        put_resp = await client.put("/api/v2/settings/system", json=settings)
        assert put_resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_put_settings_partial_update():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Try partial update (just UI settings)
        partial_settings = {
            "ui": {
                "theme": "retro-green",
                "auto_refresh": False
            }
        }
        
        put_resp = await client.put("/api/v2/settings/system", json=partial_settings)
        assert put_resp.status_code == 200
        
        # Verify only UI was updated, other sections preserved
        verify_resp = await client.get("/api/v2/settings/system")
        body = verify_resp.json()
        assert body["ui"]["theme"] == "retro-green"
        assert body["ui"]["auto_refresh"] is False
        # Hardware section should still exist
        assert "hardware" in body
