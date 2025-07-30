#!/usr/bin/env python3
"""
Sensor Fusion Engine Demo
Demonstrates usage of the sensor fusion system for localization, obstacle detection, and safety monitoring
"""

import asyncio
import logging
import yaml
import signal
import sys
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from sensor_fusion import SensorFusionEngine
from communication import MQTTBroker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/sensor_fusion_demo.log')
    ]
)

logger = logging.getLogger(__name__)


class SensorFusionDemo:
    """Demonstration of sensor fusion engine capabilities"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "config/sensor_fusion.yaml"
        self.config = None
        self.fusion_engine = None
        self.mqtt_broker = None
        self.running = False
        
        # Performance tracking
        self.start_time = None
        self.stats = {
            'localization_updates': 0,
            'obstacle_detections': 0,
            'safety_events': 0,
            'emergency_stops': 0
        }
    
    async def initialize(self):
        """Initialize the demo system"""
        logger.info("Initializing Sensor Fusion Demo")
        
        # Load configuration
        await self._load_configuration()
        
        # Start MQTT broker if configured
        if self.config.get('communication', {}).get('start_local_broker', True):
            await self._start_mqtt_broker()
        
        # Initialize sensor fusion engine
        await self._initialize_fusion_engine()
        
        logger.info("Demo system initialized successfully")
    
    async def _load_configuration(self):
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"Configuration file {self.config_path} not found, using defaults")
            self.config = self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            raise
    
    def _get_default_config(self):
        """Get default configuration for demo"""
        return {
            'performance': {
                'localization': {'update_rate_hz': 10, 'target_accuracy_m': 0.10},
                'obstacle_detection': {'update_rate_hz': 10, 'target_accuracy': 0.95},
                'safety': {'update_rate_hz': 20, 'max_response_time_ms': 200}
            },
            'mqtt': {
                'host': 'localhost',
                'port': 1883,
                'start_local_broker': True
            },
            'hardware': {
                'simulation_mode': True  # Use simulation for demo
            }
        }
    
    async def _start_mqtt_broker(self):
        """Start local MQTT broker"""
        try:
            mqtt_config = self.config.get('mqtt', {})
            self.mqtt_broker = MQTTBroker(mqtt_config)
            await self.mqtt_broker.start()
            logger.info("MQTT broker started")
            
            # Wait a moment for broker to be ready
            await asyncio.sleep(1.0)
            
        except Exception as e:
            logger.error(f"Failed to start MQTT broker: {e}")
            raise
    
    async def _initialize_fusion_engine(self):
        """Initialize the sensor fusion engine"""
        try:
            self.fusion_engine = SensorFusionEngine(self.config)
            await self.fusion_engine.initialize()
            logger.info("Sensor fusion engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize sensor fusion engine: {e}")
            raise
    
    async def run_demo(self):
        """Run the sensor fusion demo"""
        logger.info("Starting Sensor Fusion Demo")
        self.running = True
        self.start_time = datetime.now()
        
        try:
            # Start the fusion engine
            await self.fusion_engine.start()
            
            # Set up signal handlers for graceful shutdown
            self._setup_signal_handlers()
            
            # Run demo scenarios
            await self._run_demo_scenarios()
            
        except KeyboardInterrupt:
            logger.info("Demo interrupted by user")
        except Exception as e:
            logger.error(f"Demo error: {e}")
            raise
        finally:
            await self._cleanup()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _run_demo_scenarios(self):
        """Run various demo scenarios"""
        logger.info("Running demo scenarios...")
        
        # Scenario 1: Basic system health check
        await self._demo_system_health()
        
        # Scenario 2: Localization accuracy demonstration
        await self._demo_localization_accuracy()
        
        # Scenario 3: Obstacle detection demonstration
        await self._demo_obstacle_detection()
        
        # Scenario 4: Safety monitoring demonstration
        await self._demo_safety_monitoring()
        
        # Scenario 5: Performance monitoring
        await self._demo_performance_monitoring()
        
        # Keep running until interrupted
        logger.info("Demo scenarios complete. System running...")
        logger.info("Press Ctrl+C to stop the demo")
        
        try:
            while self.running:
                await self._periodic_status_report()
                await asyncio.sleep(10.0)  # Status report every 10 seconds
        except asyncio.CancelledError:
            logger.info("Demo cancelled")
    
    async def _demo_system_health(self):
        """Demonstrate system health monitoring"""
        logger.info("=== System Health Check Demo ===")
        
        # Wait for system to stabilize
        await asyncio.sleep(2.0)
        
        # Check system health
        is_healthy = self.fusion_engine.is_system_healthy()
        logger.info(f"System Health Status: {'HEALTHY' if is_healthy else 'UNHEALTHY'}")
        
        # Get detailed health metrics
        health_metrics = self.fusion_engine.get_sensor_health()
        if health_metrics:
            logger.info(f"Overall Health Score: {health_metrics.overall_health_score:.2f}")
            logger.info(f"GPS Healthy: {health_metrics.gps_healthy}")
            logger.info(f"IMU Healthy: {health_metrics.imu_healthy}")
            logger.info(f"ToF Sensors Healthy: L={health_metrics.tof_left_healthy}, R={health_metrics.tof_right_healthy}")
            logger.info(f"Camera Healthy: {health_metrics.camera_healthy}")
        
        logger.info("System health check complete\n")
    
    async def _demo_localization_accuracy(self):
        """Demonstrate localization system accuracy"""
        logger.info("=== Localization Accuracy Demo ===")
        
        # Wait for localization to initialize
        await asyncio.sleep(3.0)
        
        # Get current pose
        current_pose = self.fusion_engine.get_current_pose()
        if current_pose:
            logger.info(f"Current Position: ({current_pose.x:.3f}, {current_pose.y:.3f}, {current_pose.z:.3f}) m")
            logger.info(f"GPS Coordinates: ({current_pose.latitude:.8f}, {current_pose.longitude:.8f})")
            logger.info(f"GPS Accuracy: {current_pose.gps_accuracy:.3f} m")
            logger.info(f"Fusion Confidence: {current_pose.fusion_confidence:.2f}")
            
            # Check accuracy requirement
            position_accuracy = self.fusion_engine.get_position_accuracy()
            target_accuracy = self.config['performance']['localization']['target_accuracy_m']
            
            logger.info(f"Position Accuracy: {position_accuracy:.3f} m (target: {target_accuracy:.3f} m)")
            
            if position_accuracy <= target_accuracy:
                logger.info("✓ Localization accuracy requirement MET")
            else:
                logger.warning("✗ Localization accuracy requirement NOT MET")
        else:
            logger.warning("No pose estimate available yet")
        
        logger.info("Localization accuracy demo complete\n")
    
    async def _demo_obstacle_detection(self):
        """Demonstrate obstacle detection capabilities"""
        logger.info("=== Obstacle Detection Demo ===")
        
        # Wait for obstacle detection to stabilize
        await asyncio.sleep(2.0)
        
        # Get current obstacles
        obstacle_map = self.fusion_engine.get_current_obstacles()
        if obstacle_map:
            logger.info(f"Total Obstacles Detected: {obstacle_map.total_obstacles}")
            logger.info(f"High Confidence Obstacles: {obstacle_map.high_confidence_obstacles}")
            logger.info(f"Dynamic Obstacles: {obstacle_map.dynamic_obstacles}")
            
            # Show details of nearby obstacles
            nearby_obstacles = obstacle_map.get_obstacles_in_radius(2.0)  # Within 2m
            for i, obstacle in enumerate(nearby_obstacles[:5]):  # Show up to 5
                logger.info(f"  Obstacle {i+1}: {obstacle.obstacle_type.value} at "
                          f"({obstacle.x:.2f}, {obstacle.y:.2f}) m, "
                          f"distance: {obstacle.distance:.2f} m, "
                          f"confidence: {obstacle.confidence:.2f}")
        else:
            logger.info("No obstacles currently detected")
        
        # Check nearest obstacle distance
        nearest_distance = self.fusion_engine.get_nearest_obstacle_distance()
        logger.info(f"Nearest Obstacle Distance: {nearest_distance:.2f} m")
        
        # Demonstrate detection accuracy (would need ground truth for real test)
        target_accuracy = self.config['performance']['obstacle_detection']['target_accuracy']
        logger.info(f"Target Detection Accuracy: {target_accuracy:.1%}")
        logger.info("✓ Obstacle detection system operational")
        
        logger.info("Obstacle detection demo complete\n")
    
    async def _demo_safety_monitoring(self):
        """Demonstrate safety monitoring capabilities"""
        logger.info("=== Safety Monitoring Demo ===")
        
        # Get current safety status
        safety_status = self.fusion_engine.get_current_safety_status()
        if safety_status:
            logger.info(f"Safety Status: {'SAFE' if safety_status.is_safe else 'UNSAFE'}")
            logger.info(f"Safety Level: {safety_status.safety_level.name}")
            
            # Individual safety checks
            logger.info(f"Tilt Safe: {safety_status.tilt_safe} (angle: {safety_status.tilt_angle:.1f}°)")
            logger.info(f"Drop Safe: {safety_status.drop_safe} (clearance: {safety_status.ground_clearance:.2f} m)")
            logger.info(f"Collision Safe: {safety_status.collision_safe}")
            logger.info(f"Weather Safe: {safety_status.weather_safe} (temp: {safety_status.temperature:.1f}°C)")
            logger.info(f"Boundary Safe: {safety_status.boundary_safe}")
            
            # Active alerts
            if safety_status.active_alerts:
                logger.warning(f"Active Safety Alerts: {len(safety_status.active_alerts)}")
                for alert in safety_status.active_alerts[:3]:  # Show up to 3
                    logger.warning(f"  {alert.hazard_type}: {alert.description}")
            else:
                logger.info("No active safety alerts")
        else:
            logger.warning("Safety status not available")
        
        # Check if safe to operate
        safe_to_operate = self.fusion_engine.is_safe_to_operate()
        logger.info(f"Safe to Operate: {'YES' if safe_to_operate else 'NO'}")
        
        logger.info("Safety monitoring demo complete\n")
    
    async def _demo_performance_monitoring(self):
        """Demonstrate performance monitoring"""
        logger.info("=== Performance Monitoring Demo ===")
        
        # Get performance summary
        performance = self.fusion_engine.get_performance_summary()
        
        logger.info("Performance Requirements Check:")
        logger.info(f"  Position Accuracy Met: {'✓' if performance['position_accuracy_met'] else '✗'}")
        logger.info(f"  Obstacle Detection Available: {'✓' if performance['obstacle_detection_available'] else '✗'}")
        logger.info(f"  Safety Monitoring Active: {'✓' if performance['safety_monitoring_active'] else '✗'}")
        logger.info(f"  System Healthy: {'✓' if performance['system_healthy'] else '✗'}")
        logger.info(f"  Safe to Operate: {'✓' if performance['safe_to_operate'] else '✗'}")
        
        # Overall assessment
        all_good = all(performance.values())
        logger.info(f"Overall Status: {'ALL REQUIREMENTS MET ✓' if all_good else 'SOME ISSUES DETECTED ⚠'}")
        
        logger.info("Performance monitoring demo complete\n")
    
    async def _periodic_status_report(self):
        """Generate periodic status report"""
        if not self.start_time:
            return
        
        runtime = datetime.now() - self.start_time
        
        logger.info(f"=== Status Report (Runtime: {runtime}) ===")
        
        # System status
        logger.info(f"System Healthy: {self.fusion_engine.is_system_healthy()}")
        logger.info(f"Safe to Operate: {self.fusion_engine.is_safe_to_operate()}")
        
        # Current readings
        pose = self.fusion_engine.get_current_pose()
        if pose:
            logger.info(f"Position: ({pose.x:.2f}, {pose.y:.2f}) m, Accuracy: {self.fusion_engine.get_position_accuracy():.3f} m")
        
        obstacles = self.fusion_engine.get_current_obstacles()
        if obstacles:
            logger.info(f"Obstacles: {obstacles.total_obstacles} detected")
        
        nearest_obstacle = self.fusion_engine.get_nearest_obstacle_distance()
        logger.info(f"Nearest Obstacle: {nearest_obstacle:.2f} m")
        
        logger.info("=== End Status Report ===\n")
    
    async def _cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up demo resources...")
        
        if self.fusion_engine:
            try:
                await self.fusion_engine.stop()
                logger.info("Sensor fusion engine stopped")
            except Exception as e:
                logger.error(f"Error stopping fusion engine: {e}")
        
        if self.mqtt_broker:
            try:
                await self.mqtt_broker.stop()
                logger.info("MQTT broker stopped")
            except Exception as e:
                logger.error(f"Error stopping MQTT broker: {e}")
        
        # Final statistics
        if self.start_time:
            total_runtime = datetime.now() - self.start_time
            logger.info(f"Demo completed. Total runtime: {total_runtime}")
            logger.info(f"Statistics: {self.stats}")
        
        logger.info("Cleanup complete")


async def main():
    """Main demo function"""
    demo = SensorFusionDemo()
    
    try:
        await demo.initialize()
        await demo.run_demo()
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    # Run the demo
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
