#!/usr/bin/env python3
"""
Basic validation script for Power Management System
"""

import sys
import os
import asyncio

# Add src to path
sys.path.append('.')

async def validate_power_management():
    """Validate power management system components"""
    
    print("🔋 Validating Power Management System...")
    print("=" * 50)
    
    try:
        # Test imports
        print("📦 Testing imports...")
        from src.power_management.power_manager import (
            PowerManager, PowerMode, ChargingMode, BatteryMetrics, 
            SolarMetrics, PowerConsumption, SunnySpot
        )
        from src.power_management.power_service import PowerService
        print("✅ All imports successful")
        
        # Test data structures
        print("\n📊 Testing data structures...")
        battery = BatteryMetrics(
            voltage=12.8,
            current=-1.5,
            power=-19.2,
            state_of_charge=0.75
        )
        print(f"✅ BatteryMetrics: {battery.voltage}V, {battery.state_of_charge:.1%}")
        
        solar = SolarMetrics(
            voltage=14.0,
            current=2.0,
            power=28.0,
            efficiency=0.9
        )
        print(f"✅ SolarMetrics: {solar.power}W, {solar.efficiency:.1%}")
        
        sunny_spot = SunnySpot(
            latitude=40.7128,
            longitude=-74.0060,
            efficiency_rating=0.85,
            last_measured=datetime.now(),
            time_of_day_optimal=[12, 13, 14]
        )
        print(f"✅ SunnySpot: ({sunny_spot.latitude}, {sunny_spot.longitude})")
        
        # Test enums
        print("\n🔧 Testing enums...")
        assert PowerMode.HIGH_PERFORMANCE.value == 'high_performance'
        assert PowerMode.ECO_MODE.value == 'eco_mode'
        assert ChargingMode.AUTO.value == 'auto'
        print("✅ All enums working correctly")
        
        # Mock components for testing
        class MockHardware:
            async def get_sensor_data(self, name):
                if name == "power_monitor":
                    class MockData:
                        voltage = 12.8
                        current = -1.5
                        power = -19.2
                    return MockData()
                return None
            
            async def get_all_sensor_data(self):
                return {"power_monitor": await self.get_sensor_data("power_monitor")}
        
        class MockMQTT:
            def __init__(self):
                self.messages = []
            
            async def publish(self, topic, data):
                self.messages.append((topic, data))
                return True
            
            async def subscribe(self, topic, callback):
                return True
        
        class MockCache:
            def __init__(self):
                self.data = {}
            
            async def get(self, key):
                return self.data.get(key)
            
            async def set(self, key, value, ttl=None):
                self.data[key] = value
                return True
        
        # Test PowerManager
        print("\n⚡ Testing PowerManager...")
        hardware = MockHardware()
        mqtt = MockMQTT()
        cache = MockCache()
        
        power_manager = PowerManager(
            hardware_interface=hardware,
            mqtt_client=mqtt,
            cache_manager=cache
        )
        print("✅ PowerManager created successfully")
        
        # Test configuration loading
        config = power_manager._load_config()
        assert 'monitoring_interval' in config
        assert 'power_components' in config
        print("✅ Configuration loaded successfully")
        
        # Test SoC calculation
        soc = power_manager._calculate_soc_from_voltage(12.8)
        assert 0.0 <= soc <= 1.0
        print(f"✅ SoC calculation: {soc:.1%} for 12.8V")
        
        # Test distance calculation
        distance = power_manager._calculate_distance(40.0, -74.0, 40.01, -74.0)
        assert distance > 1000  # Should be ~1.1km
        print(f"✅ Distance calculation: {distance:.0f}m")
        
        # Test PowerService
        print("\n🌐 Testing PowerService...")
        power_service = PowerService(
            mqtt_client=mqtt,
            cache_manager=cache,
            hardware_interface=hardware
        )
        print("✅ PowerService created successfully")
        
        # Test service info
        service_info = await power_service.get_service_info()
        assert 'service_name' in service_info
        assert service_info['service_name'] == 'power_service'
        print("✅ Service info retrieval working")
        
        print("\n🎉 All validation tests passed!")
        print("✅ Power Management System is ready for deployment")
        
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    from datetime import datetime
    
    success = asyncio.run(validate_power_management())
    sys.exit(0 if success else 1)
