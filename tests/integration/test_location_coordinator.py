"""
Integration tests for Location Coordinator Service
Tests GPS hardware prioritization and config fallback functionality
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json

from src.location import LocationCoordinator, LocationData, LocationSource, GPSHealthStatus
from src.communication import MQTTClient


class MockMQTTClient:
    """Mock MQTT client for testing"""
    
    def __init__(self):
        self.published_messages = []
        self.subscriptions = {}
        self.connected = True
    
    async def publish_message(self, topic: str, message: dict, qos: int = 1):
        """Mock publish message"""
        self.published_messages.append({
            'topic': topic,
            'message': message,
            'qos': qos,
            'timestamp': datetime.now()
        })
        return True
    
    async def subscribe(self, topic: str, callback, qos: int = 1):
        """Mock subscribe"""
        self.subscriptions[topic] = callback
        return True
    
    def is_connected(self):
        """Mock connection status"""
        return self.connected


@pytest.fixture
async def mock_mqtt_client():
    """Create mock MQTT client"""
    return MockMQTTClient()


@pytest.fixture
async def location_coordinator(mock_mqtt_client, tmp_path):
    """Create location coordinator with test config"""
    # Create test config file
    test_config = tmp_path / "test_weather.yaml"
    test_config.write_text("""
location:
  latitude: 40.7128
  longitude: -74.0060
""")
    
    coordinator = LocationCoordinator(mock_mqtt_client, str(test_config))
    return coordinator


@pytest.mark.asyncio
class TestLocationCoordinator:
    """Test location coordinator functionality"""
    
    async def test_initialization_with_config_fallback(self, location_coordinator):
        """Test that coordinator initializes with config fallback"""
        await location_coordinator.start()
        
        current_location = location_coordinator.get_current_location()
        assert current_location is not None
        assert current_location.source == LocationSource.CONFIG_FALLBACK
        assert current_location.latitude == 40.7128
        assert current_location.longitude == -74.0060
        assert current_location.fix_type == "config"
        
        await location_coordinator.stop()
    
    async def test_gps_hardware_priority(self, location_coordinator, mock_mqtt_client):
        """Test that GPS hardware data takes priority over config"""
        await location_coordinator.start()
        
        # Simulate GPS data reception
        gps_callback = mock_mqtt_client.subscriptions.get("sensors/gps/data")
        assert gps_callback is not None
        
        gps_message = {
            'timestamp': datetime.now().isoformat(),
            'value': {
                'latitude': 41.0000,
                'longitude': -75.0000,
                'altitude': 100.0,
                'accuracy': 2.0,
                'satellites': 8,
                'fix_type': 'rtk'
            }
        }
        
        await gps_callback("sensors/gps/data", gps_message)
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        current_location = location_coordinator.get_current_location()
        assert current_location.source == LocationSource.GPS_HARDWARE
        assert current_location.latitude == 41.0000
        assert current_location.longitude == -75.0000
        assert current_location.satellites == 8
        assert current_location.fix_type == 'rtk'
        
        await location_coordinator.stop()
    
    async def test_gps_health_monitoring(self, location_coordinator, mock_mqtt_client):
        """Test GPS health monitoring and fallback switching"""
        await location_coordinator.start()
        
        # Send initial GPS data
        gps_callback = mock_mqtt_client.subscriptions.get("sensors/gps/data")
        gps_message = {
            'timestamp': datetime.now().isoformat(),
            'value': {
                'latitude': 41.0000,
                'longitude': -75.0000,
                'altitude': 100.0,
                'accuracy': 2.0,
                'satellites': 8,
                'fix_type': 'rtk'
            }
        }
        
        await gps_callback("sensors/gps/data", gps_message)
        await asyncio.sleep(0.1)
        
        # Verify GPS is healthy
        gps_health = location_coordinator.get_gps_health()
        assert gps_health.is_available
        assert gps_health.is_healthy
        
        # Wait for GPS timeout (simulate GPS failure)
        location_coordinator.gps_timeout_seconds = 0.2
        await asyncio.sleep(0.5)
        
        # Check that it switched to fallback
        current_location = location_coordinator.get_current_location()
        assert current_location.source == LocationSource.CONFIG_FALLBACK
        
        gps_health = location_coordinator.get_gps_health()
        assert not gps_health.is_available
        
        await location_coordinator.stop()
    
    async def test_coordinate_validation(self, location_coordinator, mock_mqtt_client):
        """Test coordinate validation for both GPS and config sources"""
        await location_coordinator.start()
        
        gps_callback = mock_mqtt_client.subscriptions.get("sensors/gps/data")
        
        # Test invalid coordinates (out of range)
        invalid_message = {
            'timestamp': datetime.now().isoformat(),
            'value': {
                'latitude': 91.0,  # Invalid latitude
                'longitude': -75.0000,
                'accuracy': 2.0,
                'satellites': 8,
                'fix_type': 'rtk'
            }
        }
        
        await gps_callback("sensors/gps/data", invalid_message)
        await asyncio.sleep(0.1)
        
        # Should still be using config fallback
        current_location = location_coordinator.get_current_location()
        assert current_location.source == LocationSource.CONFIG_FALLBACK
        
        # Test valid coordinates
        valid_message = {
            'timestamp': datetime.now().isoformat(),
            'value': {
                'latitude': 41.0000,
                'longitude': -75.0000,
                'accuracy': 2.0,
                'satellites': 8,
                'fix_type': 'rtk'
            }
        }
        
        await gps_callback("sensors/gps/data", valid_message)
        await asyncio.sleep(0.1)
        
        # Should now use GPS
        current_location = location_coordinator.get_current_location()
        assert current_location.source == LocationSource.GPS_HARDWARE
        
        await location_coordinator.stop()
    
    async def test_location_publishing(self, location_coordinator, mock_mqtt_client):
        """Test that location data is published to MQTT"""
        location_coordinator.publish_interval = 0.1  # Fast publishing for test
        await location_coordinator.start()
        
        # Wait for publishing
        await asyncio.sleep(0.2)
        
        # Check that location was published
        location_messages = [
            msg for msg in mock_mqtt_client.published_messages
            if msg['topic'] == 'location/current'
        ]
        
        assert len(location_messages) > 0
        
        latest_message = location_messages[-1]
        assert 'latitude' in latest_message['message']
        assert 'longitude' in latest_message['message']
        assert 'source' in latest_message['message']
        
        await location_coordinator.stop()
    
    async def test_location_callbacks(self, location_coordinator, mock_mqtt_client):
        """Test location update callbacks"""
        await location_coordinator.start()
        
        callback_called = []
        
        def test_callback(location_data: LocationData):
            callback_called.append(location_data)
        
        location_coordinator.register_location_callback("test", test_callback)
        
        # Trigger GPS update
        gps_callback = mock_mqtt_client.subscriptions.get("sensors/gps/data")
        gps_message = {
            'timestamp': datetime.now().isoformat(),
            'value': {
                'latitude': 41.0000,
                'longitude': -75.0000,
                'accuracy': 2.0,
                'satellites': 8,
                'fix_type': 'rtk'
            }
        }
        
        await gps_callback("sensors/gps/data", gps_message)
        
        # Wait for callback processing
        await asyncio.sleep(0.2)
        
        assert len(callback_called) > 0
        assert callback_called[-1].source == LocationSource.GPS_HARDWARE
        
        location_coordinator.unregister_location_callback("test")
        await location_coordinator.stop()
    
    async def test_update_fallback_coordinates(self, location_coordinator, tmp_path):
        """Test updating fallback coordinates"""
        await location_coordinator.start()
        
        # Update fallback coordinates
        new_lat, new_lon = 42.0000, -76.0000
        await location_coordinator.update_fallback_coordinates(new_lat, new_lon)
        
        # Verify fallback was updated
        fallback_location = location_coordinator._fallback_location
        assert fallback_location.latitude == new_lat
        assert fallback_location.longitude == new_lon
        
        await location_coordinator.stop()
    
    async def test_get_current_coordinates_tuple(self, location_coordinator):
        """Test getting coordinates as tuple"""
        await location_coordinator.start()
        
        coords = location_coordinator.get_current_coordinates()
        assert isinstance(coords, tuple)
        assert len(coords) == 2
        assert coords == (40.7128, -74.0060)  # Config fallback coordinates
        
        await location_coordinator.stop()


@pytest.mark.asyncio 
class TestLocationCoordinatorServiceIntegration:
    """Test integration with other services"""
    
    async def test_weather_service_integration(self, location_coordinator, mock_mqtt_client):
        """Test that weather service can get location from coordinator"""
        await location_coordinator.start()
        
        # Simulate weather service getting coordinates
        lat, lon = location_coordinator.get_current_coordinates()
        assert lat == 40.7128  # Default config coordinates
        assert lon == -74.0060
        
        # Update with GPS data
        gps_callback = mock_mqtt_client.subscriptions.get("sensors/gps/data")
        gps_message = {
            'timestamp': datetime.now().isoformat(),
            'value': {
                'latitude': 41.5000,
                'longitude': -75.5000,
                'accuracy': 2.0,
                'satellites': 8,
                'fix_type': 'rtk'
            }
        }
        
        await gps_callback("sensors/gps/data", gps_message)
        await asyncio.sleep(0.1)
        
        # Weather service should get updated coordinates
        lat, lon = location_coordinator.get_current_coordinates()
        assert lat == 41.5000
        assert lon == -75.5000
        
        await location_coordinator.stop()
    
    async def test_maps_service_integration(self, location_coordinator, mock_mqtt_client):
        """Test that maps can center on active coordinates"""
        await location_coordinator.start()
        
        # Check published location data format for maps
        await asyncio.sleep(0.2)
        
        location_messages = [
            msg for msg in mock_mqtt_client.published_messages
            if msg['topic'] == 'location/current'
        ]
        
        assert len(location_messages) > 0
        
        latest_message = location_messages[-1]['message']
        
        # Verify format expected by maps service
        assert 'latitude' in latest_message
        assert 'longitude' in latest_message
        assert 'source' in latest_message
        assert 'health_status' in latest_message
        
        await location_coordinator.stop()
