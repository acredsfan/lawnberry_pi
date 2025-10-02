"""Unit tests for MapsService."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from shapely.geometry import Polygon

from backend.src.services.maps_service import MapsService
from backend.src.models.maps import (
    MapConfiguration,
    WorkingBoundary,
    ExclusionZone,
    Marker,
    LatLng,
)


@pytest.fixture
def sample_boundary():
    """Create a sample working boundary."""
    return WorkingBoundary(
        polygon=[
            LatLng(lat=40.0, lng=-75.0),
            LatLng(lat=40.0, lng=-74.9),
            LatLng(lat=39.9, lng=-74.9),
            LatLng(lat=39.9, lng=-75.0),
        ]
    )


@pytest.fixture
def sample_exclusion_zone():
    """Create a sample exclusion zone."""
    return ExclusionZone(
        zone_id="zone1",
        name="Flower Bed",
        polygon=[
            LatLng(lat=39.95, lng=-74.95),
            LatLng(lat=39.95, lng=-74.94),
            LatLng(lat=39.94, lng=-74.94),
            LatLng(lat=39.94, lng=-74.95),
        ],
    )


@pytest.fixture
def sample_marker():
    """Create a sample marker."""
    return Marker(
        marker_id="marker1",
        name="Charging Station",
        position=LatLng(lat=39.95, lng=-74.95),
        icon="charging",
    )


@pytest.fixture
def sample_config(sample_boundary, sample_exclusion_zone, sample_marker):
    """Create a sample map configuration."""
    return MapConfiguration(
        config_id="config1",
        provider="leaflet",
        api_key=None,
        working_boundary=sample_boundary,
        exclusion_zones=[sample_exclusion_zone],
        markers=[sample_marker],
        last_modified=datetime.now(),
        validated=True,
    )


@pytest.fixture
def mock_persistence():
    """Mock persistence layer."""
    with patch("backend.src.services.maps_service.persistence") as mock:
        yield mock


class TestMapsService:
    """Test suite for MapsService."""

    def test_initialization_with_leaflet(self):
        """Test service initializes with Leaflet provider."""
        service = MapsService(provider="leaflet")
        assert service.current_provider == "leaflet"

    def test_initialization_with_google_maps(self):
        """Test service initializes with Google Maps provider."""
        service = MapsService(provider="google", api_key="test_key")
        assert service.current_provider == "google"

    def test_initialization_missing_google_api_key(self):
        """Test initialization fails without Google API key."""
        with pytest.raises(ValueError, match="Google Maps requires an API key"):
            MapsService(provider="google")

    def test_attempt_provider_fallback_to_leaflet(self):
        """Test fallback to Leaflet when Google fails."""
        service = MapsService(provider="google", api_key="invalid_key")
        
        success = service.attempt_provider_fallback()
        
        assert success is True
        assert service.current_provider == "leaflet"

    def test_attempt_provider_fallback_already_leaflet(self):
        """Test no fallback when already using Leaflet."""
        service = MapsService(provider="leaflet")
        
        success = service.attempt_provider_fallback()
        
        assert success is False
        assert service.current_provider == "leaflet"

    def test_validate_geojson_zone_valid_polygon(self, sample_exclusion_zone):
        """Test validating a valid GeoJSON zone."""
        service = MapsService(provider="leaflet")
        
        is_valid, error = service.validate_geojson_zone(sample_exclusion_zone)
        
        assert is_valid is True
        assert error is None

    def test_validate_geojson_zone_too_few_points(self):
        """Test validation fails with insufficient points."""
        service = MapsService(provider="leaflet")
        zone = ExclusionZone(
            zone_id="invalid",
            name="Invalid",
            polygon=[LatLng(lat=40.0, lng=-75.0), LatLng(lat=40.0, lng=-74.9)],
        )
        
        is_valid, error = service.validate_geojson_zone(zone)
        
        assert is_valid is False
        assert "at least 3 points" in error.lower()

    def test_validate_geojson_zone_self_intersecting(self):
        """Test validation fails with self-intersecting polygon."""
        service = MapsService(provider="leaflet")
        zone = ExclusionZone(
            zone_id="invalid",
            name="Self-Intersecting",
            polygon=[
                LatLng(lat=40.0, lng=-75.0),
                LatLng(lat=40.0, lng=-74.9),
                LatLng(lat=39.9, lng=-75.0),
                LatLng(lat=39.9, lng=-74.9),
            ],
        )
        
        is_valid, error = service.validate_geojson_zone(zone)
        
        assert is_valid is False
        assert "self-intersecting" in error.lower()

    def test_check_overlap_no_overlap(self, sample_boundary):
        """Test no overlap between distinct zones."""
        service = MapsService(provider="leaflet")
        zone1 = ExclusionZone(
            zone_id="zone1",
            name="Zone 1",
            polygon=[
                LatLng(lat=39.95, lng=-74.95),
                LatLng(lat=39.95, lng=-74.94),
                LatLng(lat=39.94, lng=-74.94),
            ],
        )
        zone2 = ExclusionZone(
            zone_id="zone2",
            name="Zone 2",
            polygon=[
                LatLng(lat=39.93, lng=-74.93),
                LatLng(lat=39.93, lng=-74.92),
                LatLng(lat=39.92, lng=-74.92),
            ],
        )
        
        has_overlap = service.check_overlap(zone1, [zone2])
        
        assert has_overlap is False

    def test_check_overlap_detected(self):
        """Test overlap detection between zones."""
        service = MapsService(provider="leaflet")
        zone1 = ExclusionZone(
            zone_id="zone1",
            name="Zone 1",
            polygon=[
                LatLng(lat=39.95, lng=-74.95),
                LatLng(lat=39.95, lng=-74.94),
                LatLng(lat=39.94, lng=-74.94),
                LatLng(lat=39.94, lng=-74.95),
            ],
        )
        zone2 = ExclusionZone(
            zone_id="zone2",
            name="Zone 2",
            polygon=[
                LatLng(lat=39.945, lng=-74.945),  # Overlaps with zone1
                LatLng(lat=39.945, lng=-74.935),
                LatLng(lat=39.935, lng=-74.935),
                LatLng(lat=39.935, lng=-74.945),
            ],
        )
        
        has_overlap = service.check_overlap(zone2, [zone1])
        
        assert has_overlap is True

    def test_save_map_configuration(self, mock_persistence, sample_config):
        """Test saving map configuration."""
        service = MapsService(provider="leaflet")
        
        service.save_map_configuration(sample_config)
        
        mock_persistence.save_map_configuration.assert_called_once()
        saved_data = mock_persistence.save_map_configuration.call_args[0][0]
        assert saved_data["config_id"] == "config1"
        assert saved_data["provider"] == "leaflet"

    def test_load_map_configuration(self, mock_persistence, sample_config):
        """Test loading map configuration."""
        mock_persistence.load_map_configuration.return_value = sample_config.model_dump()
        service = MapsService(provider="leaflet")
        
        config = service.load_map_configuration("config1")
        
        assert config is not None
        assert config.config_id == "config1"
        assert len(config.exclusion_zones) == 1
        assert len(config.markers) == 1
        mock_persistence.load_map_configuration.assert_called_once_with("config1")

    def test_load_map_configuration_not_found(self, mock_persistence):
        """Test loading non-existent configuration."""
        mock_persistence.load_map_configuration.return_value = None
        service = MapsService(provider="leaflet")
        
        config = service.load_map_configuration("nonexistent")
        
        assert config is None

    def test_validate_configuration_success(self, sample_config):
        """Test full configuration validation success."""
        service = MapsService(provider="leaflet")
        
        errors = []
        # Validate boundary
        is_valid, error = service.validate_geojson_zone(
            ExclusionZone(
                zone_id="boundary",
                name="Boundary",
                polygon=sample_config.working_boundary.polygon,
            )
        )
        if not is_valid:
            errors.append(error)
        
        # Validate exclusion zones
        for zone in sample_config.exclusion_zones:
            is_valid, error = service.validate_geojson_zone(zone)
            if not is_valid:
                errors.append(error)
        
        assert len(errors) == 0

    def test_validate_configuration_with_overlaps(self, sample_config):
        """Test configuration validation detects overlaps."""
        service = MapsService(provider="leaflet")
        
        # Add overlapping zone
        overlapping_zone = ExclusionZone(
            zone_id="overlap",
            name="Overlapping",
            polygon=[
                LatLng(lat=39.95, lng=-74.95),
                LatLng(lat=39.95, lng=-74.94),
                LatLng(lat=39.94, lng=-74.94),
                LatLng(lat=39.94, lng=-74.95),
            ],
        )
        
        has_overlap = service.check_overlap(
            overlapping_zone, sample_config.exclusion_zones
        )
        
        assert has_overlap is True

    def test_configuration_modification_updates_timestamp(self, sample_config):
        """Test modifying configuration updates last_modified."""
        original_time = sample_config.last_modified
        
        # Simulate modification
        import time
        time.sleep(0.01)
        sample_config.last_modified = datetime.now()
        
        assert sample_config.last_modified > original_time
