import pytest
import httpx
from backend.src.main import app


@pytest.mark.asyncio
async def test_get_system_config_returns_config():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/settings/config")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        # Check for key configuration fields
        expected_fields = [
            "mowing_height_mm",
            "cutting_speed", 
            "weather_pause_enabled",
            "charging_return_threshold",
            "safety_tilt_threshold_degrees",
            "obstacle_detection_sensitivity"
        ]
        for field in expected_fields:
            assert field in body


@pytest.mark.asyncio
async def test_put_system_config_updates_config():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Get current config
        get_resp = await client.get("/api/v2/settings/config")
        current_config = get_resp.json()
        
        # Modify one field
        updated_config = current_config.copy()
        updated_config["mowing_height_mm"] = 25
        updated_config["cutting_speed"] = 0.6
        
        # Update via PUT
        put_resp = await client.put("/api/v2/settings/config", json=updated_config)
        assert put_resp.status_code == 200
        
        # Verify the changes took effect
        returned_config = put_resp.json()
        assert returned_config["mowing_height_mm"] == 25
        assert returned_config["cutting_speed"] == 0.6
        
        # Verify via GET as well
        verify_resp = await client.get("/api/v2/settings/config")
        verify_config = verify_resp.json()
        assert verify_config["mowing_height_mm"] == 25
        assert verify_config["cutting_speed"] == 0.6
