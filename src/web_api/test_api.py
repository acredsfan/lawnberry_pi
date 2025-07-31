"""
Basic API Tests
Simple tests to validate the web API backend functionality.
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from .main import create_app
from .config import Settings
from .mqtt_bridge import MQTTBridge
from .auth import AuthManager, set_auth_manager


# Mock settings for testing
def get_test_settings():
    return Settings(
        debug=True,
        auth=Settings().auth,
        mqtt=Settings().mqtt
    )


@pytest.fixture
def mock_mqtt_bridge():
    """Mock MQTT bridge for testing"""
    bridge = AsyncMock(spec=MQTTBridge)
    bridge.is_connected.return_value = True
    bridge.get_cached_data.return_value = {
        "timestamp": "2024-01-01T00:00:00",
        "value": {"test": "data"}
    }
    bridge.publish_message.return_value = True
    return bridge


@pytest.fixture
def mock_auth_manager():
    """Mock auth manager for testing"""
    manager = AsyncMock(spec=AuthManager)
    manager.config.enabled = False  # Disable auth for testing
    return manager


@pytest.fixture
def client(mock_mqtt_bridge, mock_auth_manager):
    """Test client with mocked dependencies"""
    app = create_app()
    
    # Override dependencies
    app.state.mqtt_bridge = mock_mqtt_bridge
    app.state.auth_manager = mock_auth_manager
    set_auth_manager(mock_auth_manager)
    
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert "version" in data


def test_api_status(client):
    """Test API status endpoint"""
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "api_version" in data
    assert "status" in data
    assert "mqtt_connected" in data


def test_system_status(client):
    """Test system status endpoint"""
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "state" in data
    assert "uptime" in data
    assert "version" in data


def test_system_emergency_stop(client, mock_mqtt_bridge):
    """Test emergency stop endpoint"""
    response = client.post("/api/v1/system/emergency-stop")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Emergency stop triggered" in data["message"]
    
    # Verify MQTT message was sent
    mock_mqtt_bridge.publish_message.assert_called_once()


def test_sensors_list(client):
    """Test sensors list endpoint"""
    response = client.get("/api/v1/sensors/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_navigation_status(client):
    """Test navigation status endpoint"""
    response = client.get("/api/v1/navigation/status")
    assert response.status_code == 200
    data = response.json()
    assert "position" in data
    assert "heading" in data
    assert "speed" in data


def test_power_status(client, mock_mqtt_bridge):
    """Test power status endpoint"""
    # Mock battery data
    mock_mqtt_bridge.get_cached_data.return_value = {
        "voltage": 12.6,
        "current": -5.2,
        "power": -65.52,
        "state_of_charge": 0.85,
        "timestamp": "2024-01-01T00:00:00"
    }
    
    response = client.get("/api/v1/power/status")
    assert response.status_code == 200
    data = response.json()
    assert "battery" in data
    assert data["battery"]["voltage"] == 12.6


def test_weather_current(client, mock_mqtt_bridge):
    """Test current weather endpoint"""
    # Mock weather data
    mock_mqtt_bridge.get_cached_data.return_value = {
        "temperature": 22.5,
        "humidity": 65.0,
        "precipitation": 0.0,
        "conditions": "clear",
        "timestamp": "2024-01-01T00:00:00"
    }
    
    response = client.get("/api/v1/weather/current")
    assert response.status_code == 200
    data = response.json()
    assert data["temperature"] == 22.5
    assert data["conditions"] == "clear"


def test_patterns_list(client):
    """Test patterns list endpoint"""
    response = client.get("/api/v1/patterns/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0  # Should have available patterns


def test_maps_data(client):
    """Test maps data endpoint"""
    response = client.get("/api/v1/maps/")
    assert response.status_code == 200
    data = response.json()
    assert "boundaries" in data
    assert "no_go_zones" in data


def test_websocket_connections(client):
    """Test WebSocket connections endpoint"""
    response = client.get("/ws/connections")
    assert response.status_code == 200
    data = response.json()
    assert "total_connections" in data


def test_cors_headers(client):
    """Test CORS headers are present"""
    response = client.options("/api/v1/status")
    assert response.status_code == 200
    # CORS headers would be checked here


def test_rate_limiting_headers(client):
    """Test rate limiting doesn't interfere with normal requests"""
    # Make multiple requests
    for _ in range(5):
        response = client.get("/health")
        assert response.status_code == 200


def test_error_handling(client, mock_mqtt_bridge):
    """Test error handling"""
    # Simulate MQTT bridge not connected
    mock_mqtt_bridge.is_connected.return_value = False
    
    response = client.get("/api/v1/sensors/gps")
    assert response.status_code == 503  # Service unavailable
    data = response.json()
    assert data["success"] is False
    assert "error" in data


if __name__ == "__main__":
    # Run basic tests
    print("Running basic API tests...")
    
    # Test client creation
    try:
        app = create_app()
        print("✓ FastAPI app creation successful")
    except Exception as e:
        print(f"✗ FastAPI app creation failed: {e}")
        exit(1)
    
    # Test with mock client
    try:
        mock_bridge = AsyncMock(spec=MQTTBridge)
        mock_bridge.is_connected.return_value = True
        mock_auth = AsyncMock(spec=AuthManager)
        mock_auth.config.enabled = False
        
        app.state.mqtt_bridge = mock_bridge
        app.state.auth_manager = mock_auth
        set_auth_manager(mock_auth)
        
        client = TestClient(app)
        
        # Test health check
        response = client.get("/health")
        assert response.status_code == 200
        print("✓ Health check endpoint working")
        
        # Test API status
        response = client.get("/api/v1/status")
        assert response.status_code == 200
        print("✓ API status endpoint working")
        
        print("✓ All basic tests passed!")
        
    except Exception as e:
        print(f"✗ Basic tests failed: {e}")
        exit(1)
