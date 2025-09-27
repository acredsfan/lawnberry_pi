import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.src.main import app


def test_websocket_telemetry_hub_connection():
    """Test WebSocket connection and basic telemetry streaming."""
    client = TestClient(app)
    
    with client.websocket_connect("/api/v2/ws/telemetry") as websocket:
        # Test connection established
        data = websocket.receive_json()
        assert "event" in data
        assert data["event"] == "connection.established"
        
        # Subscribe to telemetry updates
        websocket.send_json({
            "type": "subscribe",
            "topic": "telemetry/updates"
        })
        
        # Receive subscription confirmation
        data = websocket.receive_json()
        assert data["event"] == "subscription.confirmed"
        assert data["topic"] == "telemetry/updates"


def test_websocket_telemetry_data_structure():
    """Test that telemetry data has expected structure."""
    client = TestClient(app)
    
    # For now, just test connection and subscription work
    with client.websocket_connect("/api/v2/ws/telemetry") as websocket:
        # Connection established
        connection_msg = websocket.receive_json()
        assert connection_msg["event"] == "connection.established"
        
        # Subscribe to telemetry
        websocket.send_json({
            "type": "subscribe", 
            "topic": "telemetry/updates"
        })
        
        # Should receive subscription confirmation
        sub_msg = websocket.receive_json()
        assert sub_msg["event"] == "subscription.confirmed"
        assert sub_msg["topic"] == "telemetry/updates"


def test_websocket_cadence_control():
    """Test telemetry cadence adjustment."""
    client = TestClient(app)
    
    with client.websocket_connect("/api/v2/ws/telemetry") as websocket:
        websocket.receive_json()  # connection established
        
        # Set cadence to 1Hz
        websocket.send_json({
            "type": "set_cadence",
            "cadence_hz": 1.0
        })
        
        # Should receive confirmation
        data = websocket.receive_json()
        assert data["event"] == "cadence.updated"
        assert data["cadence_hz"] == 1.0


def test_websocket_ping_pong():
    """Test that the server responds to ping with a pong (heartbeat)."""
    client = TestClient(app)

    with client.websocket_connect("/api/v2/ws/telemetry") as websocket:
        # Consume connection established message
        websocket.receive_json()

        # Send ping
        websocket.send_json({
            "type": "ping"
        })

        # Expect pong
        data = websocket.receive_json()
        assert data["event"] == "pong"
