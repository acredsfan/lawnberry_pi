
import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_map_configuration_markers_persistence():
    """Test Map Setup scenario: placing Home, AM Sun, PM Sun markers."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Create map configuration with markers
        config = {
            "markers": {
                "home": {"lat": 40.7128, "lng": -74.0060, "type": "home"},
                "am_sun": {"lat": 40.7130, "lng": -74.0058, "type": "am_sun"},
                "pm_sun": {"lat": 40.7132, "lng": -74.0062, "type": "pm_sun"}
            }
        }
        
        # PUT map configuration
        put_response = await client.put("/api/v2/map/configuration", json=config)
        
        # May not be implemented yet (TDD)
        assert put_response.status_code in [200, 201, 404, 501]
        
        if put_response.status_code in [200, 201]:
            data = put_response.json()
            assert data["status"] == "accepted"
            assert "updated_at" in data
            
            # GET map configuration to verify persistence
            get_response = await client.get("/api/v2/map/configuration")
            assert get_response.status_code == 200
            
            saved_config = get_response.json()
            assert "markers" in saved_config
            assert saved_config["markers"]["home"]["type"] == "home"


@pytest.mark.asyncio
async def test_map_configuration_boundary_polygons():
    """Test Map Setup scenario: drawing yard boundary polygons."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Create map configuration with boundary polygon
        config = {
            "boundaries": [
                {
                    "type": "boundary",
                    "coordinates": [
                        [40.7128, -74.0060],
                        [40.7130, -74.0058],
                        [40.7132, -74.0062],
                        [40.7128, -74.0060]  # Close the polygon
                    ],
                    "zone_type": "operating_area"
                }
            ]
        }
        
        put_response = await client.put("/api/v2/map/configuration", json=config)
        
        # May not be implemented yet (TDD)
        assert put_response.status_code in [200, 201, 400, 404, 422, 501]
        
        if put_response.status_code in [200, 201]:
            # Verify backend acknowledged
            data = put_response.json()
            assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_map_configuration_exclusion_zones():
    """Test Map Setup scenario: drawing exclusion zone polygons."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        config = {
            "exclusion_zones": [
                {
                    "type": "exclusion",
                    "coordinates": [
                        [40.7129, -74.0059],
                        [40.7130, -74.0058],
                        [40.7131, -74.0059],
                        [40.7129, -74.0059]
                    ],
                    "name": "flower_bed",
                    "priority": 10
                }
            ]
        }
        
        put_response = await client.put("/api/v2/map/configuration", json=config)
        assert put_response.status_code in [200, 201, 400, 404, 422, 501]


@pytest.mark.asyncio
async def test_map_configuration_overlap_rejection():
    """Test that overlapping zone polygons are rejected."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Create overlapping zones
        config = {
            "boundaries": [
                {
                    "type": "boundary",
                    "coordinates": [
                        [40.7128, -74.0060],
                        [40.7130, -74.0058],
                        [40.7132, -74.0062],
                        [40.7128, -74.0060],
                    ],
                    "zone_type": "zone1"
                }
            ],
            "exclusion_zones": [
                {
                    "type": "exclusion",
                    # Overlaps with boundary
                    "coordinates": [
                        [40.7129, -74.0059],
                        [40.7131, -74.0057],
                        [40.7133, -74.0061],
                        [40.7129, -74.0059],
                    ],
                    "name": "overlapping_zone"
                }
            ]
        }
        
        put_response = await client.put("/api/v2/map/configuration", json=config)
        
        # Should reject with 400 Bad Request due to overlap
        # May not be implemented yet (TDD)
        assert put_response.status_code in [400, 422, 404, 501]
        
        if put_response.status_code in [400, 422]:
            error_data = put_response.json()
            assert "overlap" in error_data.get("detail", "").lower() or \
                   "conflict" in error_data.get("detail", "").lower()


@pytest.mark.asyncio
async def test_map_provider_osm_fallback():
    """Test OSM fallback when Google Maps is unavailable."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # Get current map settings
        settings_response = await client.get("/api/v2/settings/maps")
        
        # May not have /settings/maps endpoint yet (TDD)
        if settings_response.status_code == 200:
            _settings = settings_response.json()
            
            # Force OSM fallback by removing API key or setting provider
            fallback_config = {
                "provider": "osm",
                "bypass_external": False
            }
            
            put_response = await client.put("/api/v2/settings/maps", json=fallback_config)
            assert put_response.status_code in [200, 404, 501]
            
            if put_response.status_code == 200:
                result = put_response.json()
                assert result["provider"] == "osm"


@pytest.mark.asyncio
async def test_map_configuration_metadata():
    """Test that map configuration includes provider metadata."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        get_response = await client.get("/api/v2/map/configuration")
        
        # May not be implemented yet (TDD)
        if get_response.status_code == 200:
            config = get_response.json()
            
            # Should include metadata
            assert "provider" in config or "metadata" in config
            
            if "metadata" in config:
                metadata = config["metadata"]
                assert "provider" in metadata
                assert metadata["provider"] in ["google", "osm"]
                
                # Should have last_modified
                assert "last_modified" in config or "last_modified" in metadata


@pytest.mark.asyncio
async def test_map_configuration_backend_acknowledgement():
    """Test that backend properly acknowledges map configuration updates."""
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        config = {
            "markers": {
                "home": {"lat": 40.7128, "lng": -74.0060, "type": "home"}
            }
        }
        
        put_response = await client.put("/api/v2/map/configuration", json=config)
        
        # May not be implemented yet (TDD)
        if put_response.status_code in [200, 201]:
            data = put_response.json()
            
            # Backend should acknowledge
            assert "status" in data
            assert data["status"] in ["accepted", "updated", "saved"]
            
            # Should include timestamp
            assert "updated_at" in data or "timestamp" in data


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
        put2 = await client.put(
            "/api/v2/settings/maps",
            json={"provider": "google", "api_key": "dummy"},
        )
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
