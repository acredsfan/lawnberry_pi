#!/usr/bin/env python3
"""
Safety System Demonstration
Shows comprehensive safety monitoring with 100ms emergency response
"""

import asyncio
import logging
import yaml
from datetime import datetime, timedelta
from typing import Dict, Any

from src.communication import MQTTClient
from src.safety import SafetyService
from src.safety.safety_service import SafetyConfig
from src.hardware.data_structures import GPSReading, IMUReading, ToFReading
from src.communication.message_protocols import SensorData

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SafetySystemDemo:
    """Comprehensive safety system demonstration"""
    
    def __init__(self):
        self.mqtt_client = None
        self.safety_service = None
        self.running = False
        
    async def setup(self):
        """Setup the safety system demonstration"""
        logger.info("Setting up safety system demonstration")
        
        # Load safety configuration
        with open('config/safety.yaml', 'r') as f:
            safety_config_data = yaml.safe_load(f)
        
        # Create safety configuration
        safety_params = safety_config_data['safety']
        config = SafetyConfig(
            emergency_response_time_ms=safety_params['emergency_response_time_ms'],
            safety_update_rate_hz=safety_params['safety_update_rate_hz'],
            emergency_update_rate_hz=safety_params['emergency_update_rate_hz'],
            person_safety_radius_m=safety_params['person_safety_radius_m'],
            pet_safety_radius_m=safety_params['pet_safety_radius_m'],
            general_safety_distance_m=safety_params['general_safety_distance_m'],
            emergency_stop_distance_m=safety_params['emergency_stop_distance_m'],
            max_safe_tilt_deg=safety_params['max_safe_tilt_deg'],
            critical_tilt_deg=safety_params['critical_tilt_deg'],
            min_operating_temp_c=safety_params['min_operating_temp_c'],
            max_operating_temp_c=safety_params['max_operating_temp_c'],
            boundary_safety_margin_m=safety_params['boundary_safety_margin_m'],
            enable_weather_safety=safety_params['enable_weather_safety'],
            enable_vision_safety=safety_params['enable_vision_safety'],
            enable_boundary_enforcement=safety_params['enable_boundary_enforcement']
        )
        
        # Initialize MQTT client
        self.mqtt_client = MQTTClient()
        await self.mqtt_client.connect()
        
        # Initialize safety service
        self.safety_service = SafetyService(self.mqtt_client, config)
        
        # Register demo callbacks
        self.safety_service.register_emergency_callback(self._demo_emergency_callback)
        
        logger.info("Safety system demonstration setup complete")
    
    async def run_demonstration(self):
        """Run comprehensive safety system demonstration"""
        logger.info("Starting safety system demonstration")
        self.running = True
        
        # Start safety service
        await self.safety_service.start()
        
        # Run demonstration scenarios
        demo_tasks = [
            asyncio.create_task(self._demonstrate_sensor_monitoring()),
            asyncio.create_task(self._demonstrate_emergency_response()),
            asyncio.create_task(self._demonstrate_hazard_detection()),
            asyncio.create_task(self._demonstrate_boundary_monitoring()),
            asyncio.create_task(self._demonstrate_performance_monitoring()),
            asyncio.create_task(self._monitor_safety_status())
        ]
        
        try:
            # Run all demonstration scenarios
            await asyncio.gather(*demo_tasks)
        except KeyboardInterrupt:
            logger.info("Demonstration interrupted by user")
        except Exception as e:
            logger.error(f"Error in demonstration: {e}")
        finally:
            # Cleanup
            await self.cleanup()
    
    async def _demonstrate_sensor_monitoring(self):
        """Demonstrate sensor monitoring and safety thresholds"""
        logger.info("=== Demonstrating Sensor Monitoring ===")
        
        scenarios = [
            ("Normal Operation", self._simulate_normal_sensors),
            ("Tilt Detection", self._simulate_tilt_hazard),
            ("Collision Detection", self._simulate_collision),
            ("Temperature Hazard", self._simulate_temperature_hazard),
            ("Obstacle Detection", self._simulate_obstacle_proximity)
        ]
        
        for scenario_name, scenario_func in scenarios:
            if not self.running:
                break
            
            logger.info(f"Running scenario: {scenario_name}")
            await scenario_func()
            await asyncio.sleep(2)  # Pause between scenarios
    
    async def _demonstrate_emergency_response(self):
        """Demonstrate emergency response system"""
        logger.info("=== Demonstrating Emergency Response ===")
        
        # Test software emergency stop
        logger.info("Testing software emergency stop")
        response_time = await self._test_emergency_stop_response()
        logger.info(f"Emergency stop response time: {response_time:.1f}ms")
        
        await asyncio.sleep(3)
        
        # Test emergency acknowledgment and reset
        logger.info("Testing emergency acknowledgment and reset")
        await self._test_emergency_reset()
        
        await asyncio.sleep(2)
    
    async def _demonstrate_hazard_detection(self):
        """Demonstrate vision-based hazard detection"""
        logger.info("=== Demonstrating Hazard Detection ===")
        
        hazard_scenarios = [
            ("Person Detection", "person", 2.5, 0.95),
            ("Pet Detection", "dog", 1.2, 0.85),
            ("Child Detection", "child", 3.5, 0.90),
            ("Vehicle Detection", "car", 4.0, 0.80)
        ]
        
        for scenario_name, object_type, distance, confidence in hazard_scenarios:
            if not self.running:
                break
            
            logger.info(f"Simulating: {scenario_name}")
            await self._simulate_vision_detection(object_type, distance, confidence)
            await asyncio.sleep(2)
    
    async def _demonstrate_boundary_monitoring(self):
        """Demonstrate GPS boundary monitoring"""
        logger.info("=== Demonstrating Boundary Monitoring ===")
        
        # Set up test boundary
        await self._setup_test_boundary()
        
        boundary_scenarios = [
            ("Inside Boundary", (40.7128, -74.0060)),  # Safe position
            ("Near Boundary", (40.7130, -74.0060)),   # Close to edge
            ("Boundary Violation", (40.7135, -74.0060)), # Outside boundary
            ("No-Go Zone Entry", (40.7127, -74.0058))  # In no-go zone
        ]
        
        for scenario_name, position in boundary_scenarios:
            if not self.running:
                break
            
            logger.info(f"Testing: {scenario_name}")
            await self._simulate_gps_position(position[0], position[1])
            await asyncio.sleep(2)
    
    async def _demonstrate_performance_monitoring(self):
        """Demonstrate safety performance monitoring"""
        logger.info("=== Demonstrating Performance Monitoring ===")
        
        # Test response time measurements
        await self._test_response_time_measurement()
        
        # Test false positive detection
        await self._test_false_positive_handling()
        
        # Show safety metrics
        await self._display_safety_metrics()
    
    async def _monitor_safety_status(self):
        """Continuously monitor and display safety status"""
        while self.running:
            try:
                # Get current safety status
                if self.safety_service and self.safety_service._current_safety_status:
                    status = self.safety_service._current_safety_status
                    
                    # Display key safety indicators
                    if not status.get('overall_safe', True):
                        logger.warning(f"SAFETY ALERT: {status.get('safety_level', 'UNKNOWN')}")
                        for alert in status.get('active_alerts', []):
                            logger.warning(f"  - {alert.get('description', 'Unknown alert')}")
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring safety status: {e}")
                await asyncio.sleep(5)
    
    # Simulation methods
    async def _simulate_normal_sensors(self):
        """Simulate normal sensor readings"""
        # Simulate normal IMU reading
        await self._publish_imu_data(
            quaternion=(1.0, 0.0, 0.0, 0.0),  # No tilt
            acceleration=(0.0, 0.0, 9.81),    # Normal gravity
            angular_velocity=(0.0, 0.0, 0.0)
        )
        
        # Simulate normal ToF readings
        await self._publish_tof_data("tof_left", 1500)  # 1.5m distance
        await self._publish_tof_data("tof_right", 1800) # 1.8m distance
        
        # Simulate normal weather
        await self._publish_weather_data(22.0, 45.0, 1013.25)  # 22°C, 45% humidity
    
    async def _simulate_tilt_hazard(self):
        """Simulate dangerous tilt condition"""
        # Simulate 30° tilt (exceeds critical threshold of 25°)
        tilt_quat = self._euler_to_quaternion(30.0, 0.0, 0.0)  # 30° roll
        await self._publish_imu_data(
            quaternion=tilt_quat,
            acceleration=(0.0, 4.9, 8.5),  # Tilted acceleration
            angular_velocity=(0.0, 0.0, 0.0)
        )
    
    async def _simulate_collision(self):
        """Simulate collision detection"""
        # Simulate high acceleration indicating collision
        await self._publish_imu_data(
            quaternion=(1.0, 0.0, 0.0, 0.0),
            acceleration=(5.0, 2.0, 9.81),  # High acceleration change
            angular_velocity=(0.0, 0.0, 0.0)
        )
    
    async def _simulate_temperature_hazard(self):
        """Simulate temperature outside safe range"""
        # Simulate temperature below minimum (5°C)
        await self._publish_weather_data(2.0, 30.0, 1020.0)  # 2°C - too cold
    
    async def _simulate_obstacle_proximity(self):
        """Simulate very close obstacle"""
        # Simulate obstacle at 10cm (below emergency threshold of 15cm)
        await self._publish_tof_data("tof_left", 100)  # 10cm distance
    
    async def _simulate_vision_detection(self, object_type: str, distance: float, confidence: float):
        """Simulate vision system detection"""
        # Create mock detection data
        detection_data = {
            'detections': [{
                'object_id': f"{object_type}_{int(datetime.now().timestamp())}",
                'class': object_type,
                'confidence': confidence,
                'bbox': [0.4, 0.3, 0.2, 0.4],  # Normalized bbox
                'distance_estimate': distance
            }],
            'timestamp': datetime.now().isoformat(),
            'camera_id': 'demo_camera'
        }
        
        # Publish detection
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="vision_detection",
            data=detection_data
        )
        
        await self.mqtt_client.publish("lawnberry/vision/detections", message)
    
    async def _simulate_gps_position(self, latitude: float, longitude: float):
        """Simulate GPS position update"""
        gps_data = {
            'latitude': latitude,
            'longitude': longitude,
            'altitude': 100.0,
            'accuracy': 1.5,
            'satellites': 8,
            'timestamp': datetime.now().isoformat()
        }
        
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="gps_position",
            data=gps_data
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/gps", message)
    
    async def _setup_test_boundary(self):
        """Set up test boundary and no-go zone"""
        # Create test yard boundary (small rectangle)
        boundary_points = [
            {'latitude': 40.7125, 'longitude': -74.0065, 'point_id': 'p1'},
            {'latitude': 40.7125, 'longitude': -74.0055, 'point_id': 'p2'},
            {'latitude': 40.7135, 'longitude': -74.0055, 'point_id': 'p3'},
            {'latitude': 40.7135, 'longitude': -74.0065, 'point_id': 'p4'}
        ]
        
        boundary_data = {
            'boundary_type': 'yard_boundary',
            'points': boundary_points
        }
        
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="boundary_update",
            data=boundary_data
        )
        
        await self.mqtt_client.publish("lawnberry/maps/boundaries", message)
        
        # Create test no-go zone
        no_go_zone = {
            'zones': [{
                'zone_id': 'demo_nogo_1',
                'name': 'Test No-Go Zone',
                'zone_type': 'temporary',
                'active': True,
                'boundary_points': [
                    {'latitude': 40.7126, 'longitude': -74.0059},
                    {'latitude': 40.7126, 'longitude': -74.0057},
                    {'latitude': 40.7128, 'longitude': -74.0057},
                    {'latitude': 40.7128, 'longitude': -74.0059}
                ]
            }]
        }
        
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="no_go_zones",
            data=no_go_zone
        )
        
        await self.mqtt_client.publish("lawnberry/maps/no_go_zones", message)
    
    async def _test_emergency_stop_response(self) -> float:
        """Test emergency stop response time"""
        start_time = datetime.now()
        
        # Trigger emergency stop
        success = await self.safety_service.trigger_emergency_stop(
            reason="Demo emergency stop test",
            triggered_by="safety_demo"
        )
        
        end_time = datetime.now()
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        
        logger.info(f"Emergency stop test result: {'SUCCESS' if success else 'FAILED'}")
        
        return response_time_ms
    
    async def _test_emergency_reset(self):
        """Test emergency acknowledgment and reset"""
        # Acknowledge emergency
        await self.safety_service.emergency_controller.acknowledge_emergency("safety_demo")
        await asyncio.sleep(1)
        
        # Reset emergency
        await self.safety_service.emergency_controller.reset_emergency("safety_demo")
        logger.info("Emergency acknowledged and reset")
    
    async def _display_safety_metrics(self):
        """Display comprehensive safety metrics"""
        if self.safety_service:
            metrics = await self.safety_service.get_safety_metrics()
            
            logger.info("=== Safety Performance Metrics ===")
            logger.info(f"Service Status: {metrics.get('service_status', {})}")
            logger.info(f"Performance: {metrics.get('performance', {})}")
            logger.info(f"Safety Events: {metrics.get('safety_events', {})}")
            
            # Display component metrics
            component_metrics = metrics.get('component_metrics', {})
            for component, metrics_data in component_metrics.items():
                if metrics_data:
                    logger.info(f"{component.title()} Metrics: {metrics_data}")
    
    # Helper methods
    async def _publish_imu_data(self, quaternion, acceleration, angular_velocity):
        """Publish IMU sensor data"""
        imu_data = {
            'sensor_id': 'bno085',
            'quaternion': quaternion,
            'acceleration': acceleration,
            'angular_velocity': angular_velocity,
            'timestamp': datetime.now().isoformat()
        }
        
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="imu_reading",
            data=imu_data
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/imu", message)
    
    async def _publish_tof_data(self, sensor_id: str, distance_mm: int):
        """Publish ToF sensor data"""
        tof_data = {
            'sensor_id': sensor_id,
            'distance_mm': distance_mm,
            'range_status': 'valid',
            'timestamp': datetime.now().isoformat()
        }
        
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="tof_reading",
            data=tof_data
        )
        
        topic = f"lawnberry/sensors/{sensor_id}"
        await self.mqtt_client.publish(topic, message)
    
    async def _publish_weather_data(self, temperature: float, humidity: float, pressure: float):
        """Publish weather sensor data"""
        weather_data = {
            'sensor_id': 'bme280',
            'temperature': temperature,
            'humidity': humidity,
            'pressure': pressure,
            'timestamp': datetime.now().isoformat()
        }
        
        message = SensorData.create(
            sender="safety_demo",
            sensor_type="weather_reading",
            data=weather_data
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/weather", message)
    
    def _euler_to_quaternion(self, roll_deg: float, pitch_deg: float, yaw_deg: float):
        """Convert Euler angles to quaternion"""
        import math
        
        roll = math.radians(roll_deg)
        pitch = math.radians(pitch_deg)
        yaw = math.radians(yaw_deg)
        
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        
        return (w, x, y, z)
    
    async def _demo_emergency_callback(self, source: str, hazards):
        """Demo emergency callback"""
        logger.critical(f"EMERGENCY CALLBACK from {source}: {len(hazards)} hazards detected")
        for hazard in hazards:
            logger.critical(f"  - {hazard.get('description', 'Unknown hazard')}")
    
    async def _test_response_time_measurement(self):
        """Test response time measurement accuracy"""
        logger.info("Testing response time measurement accuracy")
        
        # Simulate multiple emergency scenarios with timing
        for i in range(3):
            start = datetime.now()
            await self._simulate_collision()
            await asyncio.sleep(0.2)  # Wait for response
            end = datetime.now()
            
            measured_time = (end - start).total_seconds() * 1000
            logger.info(f"Response test {i+1}: {measured_time:.1f}ms")
    
    async def _test_false_positive_handling(self):
        """Test false positive detection and handling"""
        logger.info("Testing false positive handling")
        
        # Simulate marginal detection that might be false positive
        await self._simulate_vision_detection("unknown_object", 5.0, 0.3)  # Low confidence
        await asyncio.sleep(1)
    
    async def cleanup(self):
        """Cleanup demonstration"""
        logger.info("Cleaning up safety system demonstration")
        self.running = False
        
        if self.safety_service:
            await self.safety_service.stop()
        
        if self.mqtt_client:
            await self.mqtt_client.disconnect()


async def main():
    """Main demonstration function"""
    demo = SafetySystemDemo()
    
    try:
        await demo.setup()
        await demo.run_demonstration()
    except Exception as e:
        logger.error(f"Demonstration failed: {e}")
        raise
    finally:
        await demo.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
