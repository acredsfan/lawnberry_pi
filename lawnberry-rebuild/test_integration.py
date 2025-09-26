#!/usr/bin/env python3
"""
Integration test to verify frontend-backend communication
Tests both REST API and WebSocket connections
"""

import requests
import asyncio
import websockets
import json
import time

BACKEND_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"

def test_rest_api():
    """Test REST API endpoints"""
    print("Testing REST API endpoints...")
    
    # Test health endpoint
    response = requests.get(f"{BACKEND_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✅ Health endpoint working")
    
    # Test dashboard status
    response = requests.get(f"{BACKEND_URL}/api/v2/dashboard/status")
    assert response.status_code == 200
    data = response.json()
    assert "navigation_state" in data
    print("✅ Dashboard status endpoint working")
    
    # Test telemetry
    response = requests.get(f"{BACKEND_URL}/api/v2/dashboard/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "timestamp" in data
    print("✅ Telemetry endpoint working")
    
    print("All REST API tests passed! ✅")

async def test_websocket():
    """Test WebSocket connection and telemetry streaming"""
    print("Testing WebSocket connection...")
    
    try:
        async with websockets.connect(f"{WS_URL}/api/v2/ws/telemetry") as websocket:
            print("✅ WebSocket connected")
            
            # Send subscription request
            subscribe_msg = {
                "action": "subscribe",
                "topic": "telemetry"
            }
            await websocket.send(json.dumps(subscribe_msg))
            
            # Wait for confirmation and telemetry messages
            messages_received = 0
            timeout = time.time() + 10  # 10 second timeout
            
            while messages_received < 3 and time.time() < timeout:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(message)
                    print(f"📡 Received: {data.get('event', 'telemetry')}")
                    messages_received += 1
                except asyncio.TimeoutError:
                    print("⏱️  Waiting for more messages...")
            
            print(f"✅ WebSocket test completed ({messages_received} messages received)")
            
    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")
        return False
    
    return True

def test_frontend_proxy():
    """Test that frontend can proxy to backend"""
    print("Testing frontend proxy...")
    
    try:
        # Test through frontend proxy
        response = requests.get("http://localhost:3000/api/dashboard/status", timeout=5)
        if response.status_code == 200:
            print("✅ Frontend proxy working")
            return True
        else:
            print(f"❌ Frontend proxy returned {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Frontend proxy test failed: {e}")
        return False

def main():
    """Run all integration tests"""
    print("🚀 Starting LawnBerry Pi v2 Integration Tests")
    print("=" * 50)
    
    # Test REST API
    try:
        test_rest_api()
    except Exception as e:
        print(f"❌ REST API tests failed: {e}")
        return False
    
    print()
    
    # Test WebSocket
    try:
        result = asyncio.run(test_websocket())
        if not result:
            return False
    except Exception as e:
        print(f"❌ WebSocket tests failed: {e}")
        return False
    
    print()
    
    # Test frontend proxy
    try:
        result = test_frontend_proxy()
        if not result:
            return False
    except Exception as e:
        print(f"❌ Frontend proxy tests failed: {e}")
        return False
    
    print()
    print("🎉 All integration tests passed!")
    print("Frontend-Backend integration is working correctly!")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)