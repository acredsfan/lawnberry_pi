"""
Power Management System Demo
Demonstrates the comprehensive power management capabilities including
battery monitoring, solar charging, and intelligent sunny spot navigation.
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.power_management.power_manager import (
    PowerManager, PowerMode, ChargingMode, BatteryMetrics, 
    SolarMetrics, PowerConsumption, SunnySpot
)
from src.power_management.power_service import PowerService


class MockHardwareInterface:
    """Mock hardware interface for demonstration"""
    
    def __init__(self):
        self._sensor_data = {}
        self.battery_voltage = 12.8
        self.battery_current = -1.5
        self.gps_lat = 40.7128
        self.gps_lon = -74.0060
        
    async def get_sensor_data(self, sensor_name: str):
        """Mock sensor data based on sensor type"""
        if sensor_name == "power_monitor":
            # Simulate battery discharge/charge cycle
            power = self.battery_voltage * self.battery_current
            
            class MockPowerData:
                def __init__(self, voltage, current, power):
                    self.voltage = voltage
                    self.current = current
                    self.power = power
            
            return MockPowerData(self.battery_voltage, self.battery_current, power)
        
        elif sensor_name == "gps":
            class MockGPSData:
                def __init__(self, lat, lon):
                    self.latitude = lat
                    self.longitude = lon
            
            return MockGPSData(self.gps_lat, self.gps_lon)
        
        elif sensor_name == "environmental":
            class MockEnvData:
                def __init__(self):
                    self.temperature = 25.0
                    self.humidity = 50.0
                    self.pressure = 1013.25
            
            return MockEnvData()
        
        return None
    
    async def get_all_sensor_data(self):
        """Mock all sensor data"""
        return {
            'power_monitor': await self.get_sensor_data('power_monitor'),
            'gps': await self.get_sensor_data('gps'),
            'environmental': await self.get_sensor_data('environmental'),
            'tof_left': {'distance': 1000, 'timestamp': datetime.now()},
            'tof_right': {'distance': 1000, 'timestamp': datetime.now()}
        }
    
    def simulate_battery_discharge(self, rate: float = 0.1):
        """Simulate battery voltage decrease"""
        self.battery_voltage = max(10.0, self.battery_voltage - rate)
    
    def simulate_solar_charging(self, current: float = 2.0):
        """Simulate solar charging"""
        self.battery_current = current
        self.battery_voltage = min(14.0, self.battery_voltage + 0.1)
    
    def move_to_location(self, lat: float, lon: float):
        """Simulate GPS movement"""
        self.gps_lat = lat
        self.gps_lon = lon


class MockMQTTClient:
    """Mock MQTT client for demonstration"""
    
    def __init__(self):
        self.published_messages = []
        self.subscriptions = {}
    
    async def publish(self, topic: str, payload: Dict[str, Any]):
        """Mock message publishing"""
        self.published_messages.append({
            'topic': topic,
            'payload': payload,
            'timestamp': datetime.now()
        })
        print(f"📡 MQTT Published to {topic}: {json.dumps(payload, indent=2, default=str)}")
    
    async def subscribe(self, topic: str, callback):
        """Mock subscription"""
        self.subscriptions[topic] = callback
        print(f"📡 MQTT Subscribed to: {topic}")
    
    def is_connected(self):
        return True


class MockCacheManager:
    """Mock cache manager for demonstration"""
    
    def __init__(self):
        self.cache = {}
    
    async def get(self, key: str):
        """Mock cache get"""
        return self.cache.get(key)
    
    async def set(self, key: str, value: Any, ttl: int = None):
        """Mock cache set"""
        self.cache[key] = value
        print(f"💾 Cache SET {key}: {value}")


class MockWeatherService:
    """Mock weather service for demonstration"""
    
    async def get_current_weather(self):
        """Mock weather data"""
        current_hour = datetime.now().hour
        # Simulate weather conditions
        if 6 <= current_hour <= 18:
            return {
                'cloud_cover': 0.3,  # 30% cloudy
                'temperature': 22.0,
                'wind_speed': 5.0
            }
        return {
            'cloud_cover': 0.8,  # Mostly cloudy at night
            'temperature': 18.0,
            'wind_speed': 3.0
        }


class PowerManagementDemo:
    """Comprehensive power management demonstration"""
    
    def __init__(self):
        self.logger = self._setup_logging()
        
        # Create mock components
        self.hardware = MockHardwareInterface()
        self.mqtt = MockMQTTClient()
        self.cache = MockCacheManager()
        self.weather = MockWeatherService()
        
        # Create power manager
        self.power_manager = None
        self.power_service = None
    
    def _setup_logging(self):
        """Setup logging for demo"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the power management system"""
        print("🔋 Initializing Power Management System Demo")
        print("=" * 60)
        
        # Create power manager
        self.power_manager = PowerManager(
            hardware_interface=self.hardware,
            mqtt_client=self.mqtt,
            cache_manager=self.cache,
            weather_service=self.weather
        )
        
        # Create power service
        self.power_service = PowerService(
            mqtt_client=self.mqtt,
            cache_manager=self.cache,
            hardware_interface=self.hardware,
            weather_service=self.weather
        )
        
        # Initialize components
        await self.power_manager.initialize()
        await self.power_service.initialize()
        
        print("✅ Power Management System initialized successfully!")
        print()
    
    async def demonstrate_battery_monitoring(self):
        """Demonstrate battery monitoring capabilities"""
        print("🔋 BATTERY MONITORING DEMONSTRATION")
        print("-" * 40)
        
        # Show initial battery status
        status = await self.power_manager.get_power_status()
        battery = status['battery']
        
        print(f"Initial Battery Status:")
        print(f"  Voltage: {battery['voltage']:.2f}V")
        print(f"  Current: {battery['current']:.2f}A")
        print(f"  Power: {battery['power']:.2f}W")
        print(f"  State of Charge: {battery['state_of_charge']:.1%}")
        print(f"  Time Remaining: {battery['time_remaining']} minutes")
        print()
        
        # Simulate battery discharge over time
        print("Simulating battery discharge cycle...")
        for i in range(5):
            await asyncio.sleep(1)
            
            # Simulate voltage drop
            self.hardware.simulate_battery_discharge(0.2)
            
            # Force update
            power_data = await self.hardware.get_sensor_data("power_monitor")
            await self.power_manager._update_battery_metrics(power_data)
            
            # Show updated status
            status = await self.power_manager.get_power_status()
            battery = status['battery']
            mode = status['mode']
            
            print(f"  Step {i+1}: {battery['voltage']:.2f}V, "
                  f"{battery['state_of_charge']:.1%} SoC, Mode: {mode}")
        
        print("✅ Battery monitoring demonstration completed!")
        print()
    
    async def demonstrate_solar_charging(self):
        """Demonstrate solar charging management"""
        print("☀️ SOLAR CHARGING DEMONSTRATION")
        print("-" * 40)
        
        # Show solar conditions throughout the day
        test_hours = [6, 9, 12, 15, 18, 21]  # Different times of day
        
        for hour in test_hours:
            # Mock time of day
            with patch('src.power_management.power_manager.datetime') as mock_datetime:
                mock_datetime.now.return_value = datetime(2024, 6, 15, hour, 0)
                mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
                
                # Read solar data
                solar_data = await self.power_manager._read_solar_data()
                
                if solar_data:
                    await self.power_manager._update_solar_metrics(solar_data)
                    status = await self.power_manager.get_power_status()
                    solar = status['solar']
                    
                    print(f"  {hour:02d}:00 - Solar Power: {solar['power']:.1f}W, "
                          f"Efficiency: {solar['efficiency']:.1%}")
                    
                    # Simulate charging if solar power is good
                    if solar['power'] > 10.0:
                        self.hardware.simulate_solar_charging(solar['power'] / 12.0)
                else:
                    print(f"  {hour:02d}:00 - No solar power (nighttime)")
        
        print("✅ Solar charging demonstration completed!")
        print()
    
    async def demonstrate_sunny_spot_learning(self):
        """Demonstrate sunny spot learning and navigation"""
        print("🗺️ SUNNY SPOT LEARNING DEMONSTRATION")
        print("-" * 40)
        
        # Simulate movement to different locations with varying solar conditions
        test_locations = [
            {'name': 'Location A', 'lat': 40.7128, 'lon': -74.0060, 'solar_power': 25.0},
            {'name': 'Location B', 'lat': 40.7130, 'lon': -74.0065, 'solar_power': 15.0},
            {'name': 'Location C', 'lat': 40.7125, 'lon': -74.0055, 'solar_power': 28.0},
            {'name': 'Location D', 'lat': 40.7135, 'lon': -74.0070, 'solar_power': 12.0},
        ]
        
        print("Learning sunny spots from different locations...")
        
        for location in test_locations:
            # Move to location
            self.hardware.move_to_location(location['lat'], location['lon'])
            
            # Set solar conditions
            self.power_manager.solar_metrics.power = location['solar_power']
            self.power_manager.solar_metrics.efficiency = location['solar_power'] / 30.0
            
            # Update sunny spot data
            await self.power_manager._update_sunny_spot_data()
            
            print(f"  📍 {location['name']}: ({location['lat']:.4f}, {location['lon']:.4f}) "
                  f"- Solar: {location['solar_power']:.1f}W")
        
        # Show learned sunny spots
        sunny_spots = await self.power_manager.get_sunny_spots()
        print(f"\n📊 Learned {len(sunny_spots)} sunny spots:")
        
        for i, spot in enumerate(sunny_spots):
            print(f"  Spot {i+1}: Efficiency {spot['efficiency_rating']:.1%} "
                  f"at ({spot['latitude']:.4f}, {spot['longitude']:.4f})")
        
        # Find and navigate to best spot
        print("\n🧭 Finding best sunny spot for current conditions...")
        best_spot = await self.power_manager._find_best_sunny_spot()
        
        if best_spot:
            print(f"Best spot: ({best_spot.latitude:.4f}, {best_spot.longitude:.4f}) "
                  f"with {best_spot.efficiency_rating:.1%} efficiency")
            
            # Simulate low battery to trigger navigation
            self.power_manager.battery_metrics.state_of_charge = 0.15
            await self.power_manager._navigate_to_sunny_spot(best_spot)
            
            print("✅ Navigation to sunny spot initiated!")
        
        print("✅ Sunny spot learning demonstration completed!")
        print()
    
    async def demonstrate_power_optimization(self):
        """Demonstrate power optimization and mode switching"""
        print("⚡ POWER OPTIMIZATION DEMONSTRATION")
        print("-" * 40)
        
        # Test different battery levels and their corresponding modes
        test_scenarios = [
            {'soc': 0.85, 'solar': 20.0, 'expected_mode': 'high_performance'},
            {'soc': 0.45, 'solar': 5.0, 'expected_mode': 'eco_mode'},
            {'soc': 0.15, 'solar': 25.0, 'expected_mode': 'charging_mode'},
            {'soc': 0.03, 'solar': 0.0, 'expected_mode': 'emergency_mode'},
        ]
        
        print("Testing power mode optimization for different scenarios...")
        
        for i, scenario in enumerate(test_scenarios):
            print(f"\n📋 Scenario {i+1}:")
            print(f"  Battery SoC: {scenario['soc']:.1%}")
            print(f"  Solar Power: {scenario['solar']:.1f}W")
            
            # Set conditions
            self.power_manager.battery_metrics.state_of_charge = scenario['soc']
            self.power_manager.solar_metrics.power = scenario['solar']
            
            # Determine optimal mode
            optimal_mode = await self.power_manager._determine_optimal_power_mode()
            print(f"  Optimal Mode: {optimal_mode.value}")
            
            # Switch to optimal mode
            if optimal_mode != self.power_manager.current_mode:
                await self.power_manager._switch_power_mode(optimal_mode)
            
            # Calculate power consumption for this mode
            await self.power_manager._calculate_power_consumption()
            consumption = self.power_manager.power_consumption
            
            print(f"  Power Consumption: {consumption.total:.1f}W")
            print(f"    CPU: {consumption.cpu:.1f}W")
            print(f"    Sensors: {consumption.sensors:.1f}W")
            print(f"    Motors: {consumption.motors:.1f}W")
        
        print("\n✅ Power optimization demonstration completed!")
        print()
    
    async def demonstrate_charging_modes(self):
        """Demonstrate different charging modes"""
        print("🔌 CHARGING MODES DEMONSTRATION")
        print("-" * 40)
        
        charging_modes = ['auto', 'manual', 'eco']
        
        for mode in charging_modes:
            print(f"\n🔧 Testing {mode.upper()} charging mode:")
            
            # Set charging mode
            result = await self.power_manager.set_charging_mode(mode)
            print(f"  Mode set successfully: {result}")
            print(f"  Current charging mode: {self.power_manager.charging_mode.value}")
            
            # Simulate conditions and show behavior
            self.power_manager.battery_metrics.state_of_charge = 0.25
            self.power_manager.solar_metrics.power = 20.0
            
            # Run optimization for this mode
            await self.power_manager._optimize_charging_strategy()
            
            await asyncio.sleep(0.5)  # Brief pause for demonstration
        
        print("\n✅ Charging modes demonstration completed!")
        print()
    
    async def demonstrate_safety_monitoring(self):
        """Demonstrate safety monitoring and alerts"""
        print("🚨 SAFETY MONITORING DEMONSTRATION")
        print("-" * 40)
        
        # Test various safety conditions
        safety_scenarios = [
            {
                'name': 'Critical Battery',
                'soc': 0.02,
                'voltage': 10.2,
                'temperature': 25.0
            },
            {
                'name': 'High Temperature', 
                'soc': 0.5,
                'voltage': 12.5,
                'temperature': 65.0
            },
            {
                'name': 'Low Voltage',
                'soc': 0.1,
                'voltage': 9.8,
                'temperature': 25.0
            }
        ]
        
        print("Testing safety monitoring for critical conditions...")
        
        for scenario in safety_scenarios:
            print(f"\n⚠️  Testing: {scenario['name']}")
            
            # Set critical conditions
            self.power_manager.battery_metrics.state_of_charge = scenario['soc']
            self.power_manager.battery_metrics.voltage = scenario['voltage']
            self.power_manager.battery_metrics.temperature = scenario['temperature']
            
            # Clear previous messages
            self.mqtt.published_messages.clear()
            
            # Perform safety checks
            await self.power_manager._perform_safety_checks()
            
            # Check for safety alerts
            safety_alerts = [
                msg for msg in self.mqtt.published_messages
                if 'safety/' in msg['topic']
            ]
            
            print(f"  Generated {len(safety_alerts)} safety alert(s)")
            for alert in safety_alerts:
                print(f"    📢 {alert['topic']}: {alert['payload'].get('message', 'N/A')}")
        
        print("\n✅ Safety monitoring demonstration completed!")
        print()
    
    async def run_demo(self):
        """Run the complete power management demonstration"""
        try:
            await self.initialize()
            
            # Run all demonstrations
            await self.demonstrate_battery_monitoring()
            await self.demonstrate_solar_charging()
            await self.demonstrate_sunny_spot_learning()
            await self.demonstrate_power_optimization()
            await self.demonstrate_charging_modes()
            await self.demonstrate_safety_monitoring()
            
            # Show final system status
            print("📊 FINAL SYSTEM STATUS")
            print("-" * 40)
            final_status = await self.power_manager.get_power_status()
            
            print(f"Battery: {final_status['battery']['state_of_charge']:.1%} SoC, "
                  f"{final_status['battery']['voltage']:.2f}V")
            print(f"Solar: {final_status['solar']['power']:.1f}W")
            print(f"Power Mode: {final_status['mode']}")
            print(f"Charging Mode: {final_status['charging_mode']}")
            print(f"Sunny Spots: {final_status['sunny_spots_count']} learned")
            print(f"Power Saving: {'Enabled' if final_status['power_saving_enabled'] else 'Disabled'}")
            
            print("\n🎉 Power Management System Demo Completed Successfully!")
            
        except Exception as e:
            self.logger.error(f"Demo failed: {e}")
            raise
        
        finally:
            # Cleanup
            if self.power_manager:
                await self.power_manager.shutdown()
            if self.power_service:
                await self.power_service.shutdown()


async def main():
    """Main demo function"""
    print("🚀 LawnBerry Pi - Power Management System Demo")
    print("=" * 60)
    print("This demo showcases the comprehensive power management capabilities:")
    print("• Real-time battery monitoring with SoC estimation")
    print("• Solar charging optimization and weather awareness")
    print("• Intelligent sunny spot learning and navigation")
    print("• Dynamic power mode optimization")
    print("• Safety monitoring and emergency responses")
    print("• MQTT-based service coordination")
    print()
    
    demo = PowerManagementDemo()
    await demo.run_demo()


if __name__ == "__main__":
    # Import patch for mocking datetime in demonstrations
    from unittest.mock import patch
    
    # Run the demo
    asyncio.run(main())
