"""Contract tests for /api/v1/maps/zones CRUD operations."""
import pytest
import httpx
from typing import List, Dict, Any


@pytest.mark.asyncio
async def test_zones_get_returns_list(test_client):
    """Test GET /api/v1/maps/zones returns a list."""
    response = await test_client.get("/api/v1/maps/zones")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_zones_post_creates_zone(test_client):
    """Test POST /api/v1/maps/zones creates new zones."""
    test_zones = [
        {
            "id": "test-zone-1",
            "name": "Front Yard",
            "polygon": [
                {"latitude": 40.7128, "longitude": -74.0060},
                {"latitude": 40.7129, "longitude": -74.0060},
                {"latitude": 40.7129, "longitude": -74.0059},
                {"latitude": 40.7128, "longitude": -74.0059}
            ],
            "priority": 1,
            "exclusion_zone": False
        }
    ]
    
    response = await test_client.post("/api/v1/maps/zones", json=test_zones)
    assert response.status_code == 200
    
    # Response should return the created zones
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    
    zone = data[0]
    assert zone["id"] == "test-zone-1"
    assert zone["name"] == "Front Yard"
    assert len(zone["polygon"]) == 4


@pytest.mark.asyncio
async def test_zones_post_invalid_polygon(test_client):
    """Test POST with invalid polygon geometry fails validation."""
    invalid_zones = [
        {
            "id": "invalid-zone",
            "name": "Invalid Zone",
            "polygon": [
                {"latitude": 40.7128, "longitude": -74.0060}
                # Only one point - invalid polygon
            ],
            "priority": 1,
            "exclusion_zone": False
        }
    ]
    
    response = await test_client.post("/api/v1/maps/zones", json=invalid_zones)
    # Should return validation error
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_zones_get_after_post_persistence(test_client):
    """Test that zones persist after creation."""
    # Create a zone
    test_zones = [
        {
            "id": "persist-test",
            "name": "Persistence Test Zone",
            "polygon": [
                {"latitude": 40.7128, "longitude": -74.0060},
                {"latitude": 40.7129, "longitude": -74.0060},
                {"latitude": 40.7129, "longitude": -74.0059},
                {"latitude": 40.7128, "longitude": -74.0059}
            ],
            "priority": 2,
            "exclusion_zone": True
        }
    ]
    
    post_response = await test_client.post("/api/v1/maps/zones", json=test_zones)
    assert post_response.status_code == 200
    
    # Retrieve zones and verify it exists
    get_response = await test_client.get("/api/v1/maps/zones")
    assert get_response.status_code == 200
    
    zones = get_response.json()
    persist_zone = next((z for z in zones if z["id"] == "persist-test"), None)
    assert persist_zone is not None
    assert persist_zone["name"] == "Persistence Test Zone"
    assert persist_zone["exclusion_zone"] is True


@pytest.mark.asyncio
async def test_zones_caching_headers(test_client):
    """Test that zones endpoint includes proper caching headers."""
    response = await test_client.get("/api/v1/maps/zones")
    assert response.status_code == 200
    
    headers = response.headers
    # Should include ETag and Last-Modified for caching
    assert "etag" in headers or "ETag" in headers
    assert "last-modified" in headers or "Last-Modified" in headers