"""Contract tests for /api/v1/status endpoint."""
import pytest


@pytest.mark.asyncio
async def test_status_endpoint_returns_200(test_client):
    """Test that /api/v1/status returns 200 OK."""
    response = await test_client.get("/api/v1/status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_status_endpoint_has_required_fields(test_client):
    """Test that status response contains required fields per contract."""
    response = await test_client.get("/api/v1/status")
    assert response.status_code == 200
    
    data = response.json()
    
    # Required fields per contract specification
    assert "battery_percentage" in data
    assert "navigation_state" in data
    assert "safety_status" in data
    assert "motor_status" in data
    assert "last_updated" in data


@pytest.mark.asyncio  
async def test_status_endpoint_field_types(test_client):
    """Test that status response fields have correct types."""
    response = await test_client.get("/api/v1/status")
    assert response.status_code == 200
    
    data = response.json()
    
    # Type validation
    if data["battery_percentage"] is not None:
        assert isinstance(data["battery_percentage"], (int, float))
        assert 0 <= data["battery_percentage"] <= 100
        
    assert isinstance(data["navigation_state"], str)
    assert isinstance(data["motor_status"], str)
    assert isinstance(data["last_updated"], str)  # ISO datetime string