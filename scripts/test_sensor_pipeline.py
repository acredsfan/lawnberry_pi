#!/usr/bin/env python3
"""
Test script for sensor data pipeline
Tests hardware → MQTT → Web API → WebSocket data flow
"""

import asyncio
import logging
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.hardware import create_hardware_interface
from src.communication.client import MQTTClient
from src.web_api.mqtt_bridge import MQTTBridge

async def test_hardware_interface():
    """Test hardware interface sensor reading"""
    print("🔧 Testing hardware interface...")
    
    try:
        async with asyncio.timeout(30.0):
            hw = create_hardware_interface()
            await hw.initialize()
            
            sensor_data = await hw.get_all_sensor_data()
            print(f"✅ Hardware interface: {len(sensor_data)} sensors detected")
            
            for sensor_id, reading in sensor_data.items():
                print(f"  📡 {sensor_id}: {reading.value} {reading.unit}")
                
            return True
            
    except asyncio.TimeoutError:
        print("❌ Hardware interface test timed out")
        return False
    except Exception as e:
        print(f"❌ Hardware interface error: {e}")
        return False

async def test_mqtt_connection():
    """Test MQTT connection and publish"""
    print("\n📡 Testing MQTT connection...")
    
    try:
        async with asyncio.timeout(15.0):
            client = MQTTClient(
                client_id="test_client",
                config={
                    'broker_host': 'localhost',
                    'broker_port': 1883,
                    'keepalive': 60,
                    'auth': {'enabled': False},
                    'tls': {'enabled': False}
                }
            )
            
            await client.connect()
            print("✅ MQTT connection successful")
            
            # Test publish
            test_data = {"test": "data", "timestamp": "2025-08-05T14:00:00Z"}
            await client.publish("lawnberry/test/data", test_data)
            print("✅ MQTT publish successful")
            
            await client.disconnect()
            return True
            
    except asyncio.TimeoutError:
        print("❌ MQTT connection test timed out")
        return False
    except Exception as e:
        print(f"❌ MQTT connection error: {e}")
        return False

async def test_web_api_endpoints():
    """Test Web API endpoints"""
    print("\n🌐 Testing Web API endpoints...")
    
    try:
        async with asyncio.timeout(10.0):
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                # Test API status
                async with session.get('http://localhost:8000/api/v1/status') as response:
                    if response.status == 200:
                        data = await response.json()
                        print("✅ Web API status endpoint working")
                        print(f"  📊 State: {data.get('state', 'unknown')}")
                        print(f"  📍 Position: {data.get('position', {})}")
                        return True
                    else:
                        print(f"❌ Web API returned status {response.status}")
                        return False
                        
    except asyncio.TimeoutError:
        print("❌ Web API test timed out")
        return False
    except Exception as e:
        print(f"❌ Web API error: {e}")
        return False

async def test_sensor_data_flow():
    """Test complete sensor data flow"""
    print("\n🔄 Testing complete sensor data flow...")
    
    try:
        # Test individual components
        hw_ok = await test_hardware_interface()
        mqtt_ok = await test_mqtt_connection()
        api_ok = await test_web_api_endpoints()
        
        if hw_ok and mqtt_ok and api_ok:
            print("\n✅ Complete sensor data pipeline test PASSED")
            return True
        else:
            print(f"\n❌ Pipeline test FAILED - HW:{hw_ok} MQTT:{mqtt_ok} API:{api_ok}")
            return False
            
    except Exception as e:
        print(f"❌ Sensor data flow test error: {e}")
        return False

async def main():
    """Main test function"""
    print("🚀 LawnBerryPi Sensor Data Pipeline Test")
    print("="*50)
    
    # Setup logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise
    
    try:
        # Run tests with overall timeout
        async with asyncio.timeout(120.0):  # 2 minute max
            success = await test_sensor_data_flow()
            
            if success:
                print("\n🎉 All tests passed! Sensor data pipeline is working.")
                sys.exit(0)
            else:
                print("\n💥 Some tests failed. Check configuration and services.")
                sys.exit(1)
                
    except asyncio.TimeoutError:
        print("\n⏰ Test suite timed out after 2 minutes")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test suite failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
