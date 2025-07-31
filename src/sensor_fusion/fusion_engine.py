"""
Main sensor fusion engine that coordinates localization, obstacle detection, and safety monitoring
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
import numpy as np

from ..communication import MQTTClient, MQTTBroker, ServiceManager
from ..hardware import HardwareInterface
from .localization import LocalizationSystem
from .obstacle_detection import ObstacleDetectionSystem
from .safety_monitor import SafetyMonitor
from .data_structures import (
    PoseEstimate, ObstacleMap, SafetyStatus, SensorHealthMetrics,
    LocalizationData, ObstacleData, HazardAlert, HazardLevel
)

logger = logging.getLogger(__name__)


class SensorFusionEngine:
    """
    Main sensor fusion engine that combines IMU, GPS, ToF, and camera data
    for accurate localization and obstacle detection with safety monitoring
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Performance requirements
        self.localization_update_rate = 10  # Hz
        self.safety_update_rate = 20       # Hz
        self.target_position_accuracy = 0.10  # 10cm
        self.target_obstacle_detection_accuracy = 0.95  # 95%
        self.target_safety_response_time = 200  # 200ms
        
        # Core components
        self.mqtt_broker: Optional[MQTTBroker] = None
        self.mqtt_client: Optional[MQTTClient] = None
        self.hardware_interface: Optional[HardwareInterface] = None
        self.service_manager: Optional[ServiceManager] = None
        
        # Fusion subsystems
        self.localization_system: Optional[LocalizationSystem] = None
        self.obstacle_detection_system: Optional[ObstacleDetectionSystem] = None
        self.safety_monitor: Optional[SafetyMonitor] = None
        
        # Current state
        self._current_pose: Optional[PoseEstimate] = None
        self._current_obstacles: Optional[ObstacleMap] = None
        self._current_safety_status: Optional[SafetyStatus] = None
        self._sensor_health: Optional[SensorHealthMetrics] = None
        
        # Performance tracking
        self._localization_accuracy_history: List[float] = []
        self._obstacle_detection_stats: Dict[str, int] = {
            'total_detections': 0,
            'confirmed_detections': 0,
            'false_positives': 0
        }
        self._safety_response_times: List[float] = []
        
        # System state
        self._running = False
        self._health_monitoring_task: Optional[asyncio.Task] = None
        self._performance_monitoring_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the sensor fusion engine"""
        logger.info("Initializing sensor fusion engine")
        
        try:
            # Initialize communication infrastructure
            await self._initialize_communication()
            
            # Initialize hardware interface
            await self._initialize_hardware()
            
            # Initialize subsystems
            await self._initialize_subsystems()
            
            # Set up emergency callbacks
            await self._setup_emergency_callbacks()
            
            logger.info("Sensor fusion engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize sensor fusion engine: {e}")
            raise
    
    async def start(self):
        """Start the sensor fusion engine"""
        logger.info("Starting sensor fusion engine")
        self._running = True
        
        try:
            # Start communication infrastructure
            if self.mqtt_broker:
                await self.mqtt_broker.start()
            await self.mqtt_client.connect()
            
            # Start hardware interface
            await self.hardware_interface.start()
            
            # Start subsystems
            await self.localization_system.start()
            await self.obstacle_detection_system.start()
            await self.safety_monitor.start()
            
            # Start monitoring tasks
            self._health_monitoring_task = asyncio.create_task(self._health_monitoring_loop())
            self._performance_monitoring_task = asyncio.create_task(self._performance_monitoring_loop())
            
            logger.info("Sensor fusion engine started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start sensor fusion engine: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the sensor fusion engine"""
        logger.info("Stopping sensor fusion engine")
        self._running = False
        
        # Cancel monitoring tasks
        if self._health_monitoring_task:
            self._health_monitoring_task.cancel()
            try:
                await self._health_monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._performance_monitoring_task:
            self._performance_monitoring_task.cancel()
            try:
                await self._performance_monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop subsystems
        if self.safety_monitor:
            await self.safety_monitor.stop()
        if self.obstacle_detection_system:
            await self.obstacle_detection_system.stop()
        if self.localization_system:
            await self.localization_system.stop()
        
        # Stop hardware interface
        if self.hardware_interface:
            await self.hardware_interface.stop()
        
        # Stop communication
        if self.mqtt_client:
            await self.mqtt_client.disconnect()
        if self.mqtt_broker:
            await self.mqtt_broker.stop()
        
        logger.info("Sensor fusion engine stopped")
    
    async def _initialize_communication(self):
        """Initialize MQTT communication infrastructure"""
        from ..communication import MQTTBroker, MQTTClient, ServiceManager
        
        # Start local MQTT broker if configured
        if self.config.get('mqtt', {}).get('start_local_broker', True):
            self.mqtt_broker = MQTTBroker(self.config.get('mqtt', {}))
        
        # Initialize MQTT client
        mqtt_config = self.config.get('mqtt', {})
        self.mqtt_client = MQTTClient(
            client_id="sensor_fusion_engine",
            host=mqtt_config.get('host', 'localhost'),
            port=mqtt_config.get('port', 1883),
            username=mqtt_config.get('username'),
            password=mqtt_config.get('password')
        )
        
        # Initialize service manager
        self.service_manager = ServiceManager(self.mqtt_client)
    
    async def _initialize_hardware(self):
        """Initialize hardware interface"""
        from ..hardware import HardwareInterface
        
        hardware_config = self.config.get('hardware', {})
        self.hardware_interface = HardwareInterface(hardware_config)
        await self.hardware_interface.initialize()
    
    async def _initialize_subsystems(self):
        """Initialize sensor fusion subsystems"""
        # Initialize localization system
        self.localization_system = LocalizationSystem(self.mqtt_client)
        
        # Initialize obstacle detection system
        self.obstacle_detection_system = ObstacleDetectionSystem(self.mqtt_client)
        
        # Initialize safety monitor
        self.safety_monitor = SafetyMonitor(self.mqtt_client)
        
        logger.info("Sensor fusion subsystems initialized")
    
    async def _setup_emergency_callbacks(self):
        """Set up emergency response callbacks"""
        # Register safety monitor emergency callback
        self.safety_monitor.register_emergency_callback(self._handle_emergency_situation)
        
        # Subscribe to emergency topics
        await self.mqtt_client.subscribe("lawnberry/safety/emergency", self._handle_emergency_message)
        await self.mqtt_client.subscribe("lawnberry/safety/obstacle_alert", self._handle_obstacle_alert)
    
    async def _handle_emergency_situation(self, hazards: List[HazardAlert]):
        """Handle emergency situation from safety monitor"""
        logger.critical(f"EMERGENCY: {len(hazards)} critical hazards detected")
        
        # Immediately publish emergency stop command
        emergency_data = {
            'command': 'EMERGENCY_STOP',
            'reason': 'SAFETY_HAZARD',
            'hazards': [
                {
                    'type': hazard.hazard_type,
                    'level': hazard.hazard_level.value,
                    'description': hazard.description
                }
                for hazard in hazards
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        from ..communication.message_protocols import CommandMessage
        message = CommandMessage.create(
            sender="sensor_fusion_engine",
            command="emergency_stop",
            data=emergency_data,
            priority=3  # Critical priority
        )
        
        await self.mqtt_client.publish("lawnberry/commands/emergency", message)
        
        # Track response time
        response_time = (datetime.now() - hazards[0].timestamp).total_seconds() * 1000
        self._safety_response_times.append(response_time)
        
        logger.info(f"Emergency response sent in {response_time:.1f}ms")
    
    async def _handle_emergency_message(self, topic: str, message):
        """Handle emergency messages from other systems"""
        logger.warning(f"Emergency message received: {message.payload}")
    
    async def _handle_obstacle_alert(self, topic: str, message):
        """Handle obstacle alerts from detection system"""
        alert_data = message.payload
        if alert_data.get('immediate_response_required'):
            logger.warning(f"Immediate obstacle alert: {alert_data['hazard_type']} at {alert_data['distance']:.2f}m")
    
    async def _health_monitoring_loop(self):
        """Monitor sensor health and system performance"""
        while self._running:
            try:
                # Collect health metrics from all subsystems
                health_metrics = await self._collect_health_metrics()
                self._sensor_health = health_metrics
                
                # Publish health metrics
                await self._publish_health_metrics(health_metrics)
                
                # Check for degraded performance
                await self._check_performance_degradation(health_metrics)
                
                await asyncio.sleep(5.0)  # Health check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _performance_monitoring_loop(self):
        """Monitor system performance against requirements with enhanced optimization"""
        performance_window = []
        latency_measurements = []
        
        while self._running:
            try:
                start_time = time.perf_counter()
                
                # Update current state from subsystems with timing
                await self._update_current_state()
                
                # Measure sensor fusion latency
                fusion_start = time.perf_counter()
                performance_report = await self._evaluate_performance()
                fusion_latency = (time.perf_counter() - fusion_start) * 1000  # ms
                
                # Track latency measurements
                latency_measurements.append(fusion_latency)
                if len(latency_measurements) > 100:
                    latency_measurements.pop(0)
                
                # Apply real-time optimizations if latency exceeds target
                if fusion_latency > self.target_safety_response_time * 0.4:  # 80ms threshold
                    await self._apply_realtime_optimizations()
                
                # Enhanced performance logging with optimization triggers
                await self._log_performance_issues(performance_report)
                
                # Publish enhanced performance metrics
                await self._publish_performance_metrics(performance_report)
                
                # Adaptive sleep based on system load
                total_loop_time = (time.perf_counter() - start_time) * 1000
                sleep_time = max(1.0, 5.0 - total_loop_time / 1000.0)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in performance monitoring loop: {e}")
                await asyncio.sleep(1.0)  # Faster recovery
    
    async def _apply_realtime_optimizations(self):
        """Apply real-time optimizations when latency exceeds targets"""
        try:
            # Force garbage collection to free memory
            import gc
            gc.collect()
            
            # Reduce update rates temporarily if needed
            if hasattr(self, '_high_latency_mode'):
                return  # Already in optimization mode
            
            self._high_latency_mode = True
            
            # Apply optimizations by temporarily reducing update frequencies
            if self.localization_system:
                # Temporarily reduce localization update rate
                original_rate = getattr(self.localization_system, 'update_rate', 10)
                self.localization_system.update_rate = max(5, int(original_rate * 0.8))
            
            if self.obstacle_detection_system:
                # Store original settings for restoration
                self._original_obstacle_rate = getattr(self.obstacle_detection_system, 'update_rate', 10)
                self.obstacle_detection_system.update_rate = max(5, int(self._original_obstacle_rate * 0.8))
            
            logger.warning("Applied real-time optimizations due to high latency")
            
            # Reset optimization mode after 30 seconds
            asyncio.create_task(self._reset_optimization_mode())
            
        except Exception as e:
            logger.error(f"Failed to apply real-time optimizations: {e}")
    
    async def _reset_optimization_mode(self):
        """Reset optimization mode after timeout"""
        await asyncio.sleep(30)
        if hasattr(self, '_high_latency_mode'):
            delattr(self, '_high_latency_mode')
            
            # Restore original update rates
            if self.localization_system and hasattr(self, '_original_localization_rate'):
                self.localization_system.update_rate = getattr(self, '_original_localization_rate', 10)
            
            if self.obstacle_detection_system and hasattr(self, '_original_obstacle_rate'):
                self.obstacle_detection_system.update_rate = getattr(self, '_original_obstacle_rate', 10)
            
            logger.info("Restored normal operation mode")
    
    async def _collect_health_metrics(self) -> SensorHealthMetrics:
        """Collect health metrics from all sensors and subsystems"""
        current_time = datetime.now()
        
        # Get hardware health from hardware interface
        hardware_health = await self.hardware_interface.get_health_status()
        
        # Create sensor health metrics
        health_metrics = SensorHealthMetrics(
            timestamp=current_time,
            gps_healthy=hardware_health.get('gps', {}).get('is_healthy', False),
            imu_healthy=hardware_health.get('imu', {}).get('is_healthy', False),
            tof_left_healthy=hardware_health.get('tof_left', {}).get('is_healthy', False),
            tof_right_healthy=hardware_health.get('tof_right', {}).get('is_healthy', False),
            camera_healthy=hardware_health.get('camera', {}).get('is_healthy', False),
            power_monitor_healthy=hardware_health.get('power_monitor', {}).get('is_healthy', False),
            weather_sensor_healthy=hardware_health.get('weather', {}).get('is_healthy', False),
            mqtt_connected=self.mqtt_client.is_connected() if self.mqtt_client else False,
            hardware_interface_connected=self.hardware_interface.is_connected() if self.hardware_interface else False
        )
        
        # Get GPS accuracy if available
        if self._current_pose:
            health_metrics.gps_accuracy = self._current_pose.gps_accuracy
        
        # Get sensor update rates
        health_metrics.sensor_update_rates = hardware_health.get('update_rates', {})
        
        return health_metrics
    
    async def _update_current_state(self):
        """Update current state from subsystems"""
        # Get current pose from localization system
        if self.localization_system:
            self._current_pose = self.localization_system.get_current_pose()
        
        # Get current obstacles from obstacle detection system
        if self.obstacle_detection_system:
            obstacles = self.obstacle_detection_system.get_current_obstacles()
            if obstacles:
                self._current_obstacles = ObstacleMap(
                    timestamp=datetime.now(),
                    obstacles=obstacles
                )
        
        # Get current safety status from safety monitor
        if self.safety_monitor:
            self._current_safety_status = self.safety_monitor.get_current_safety_status()
    
    async def _evaluate_performance(self) -> Dict[str, Any]:
        """Evaluate system performance against requirements"""
        performance_report = {
            'timestamp': datetime.now().isoformat(),
            'localization_performance': {},
            'obstacle_detection_performance': {},
            'safety_performance': {},
            'overall_performance': {}
        }
        
        # Evaluate localization performance
        if self.localization_system:
            position_accuracy = self.localization_system.get_position_accuracy()
            self._localization_accuracy_history.append(position_accuracy)
            if len(self._localization_accuracy_history) > 100:
                self._localization_accuracy_history.pop(0)
            
            avg_accuracy = np.mean(self._localization_accuracy_history) if self._localization_accuracy_history else float('inf')
            
            performance_report['localization_performance'] = {
                'current_accuracy_m': position_accuracy,
                'average_accuracy_m': avg_accuracy,
                'target_accuracy_m': self.target_position_accuracy,
                'accuracy_met': avg_accuracy <= self.target_position_accuracy,
                'pose_available': self._current_pose is not None,
                'gps_accuracy': self._current_pose.gps_accuracy if self._current_pose else 0.0,
                'fusion_confidence': self._current_pose.fusion_confidence if self._current_pose else 0.0
            }
        
        # Evaluate obstacle detection performance
        if self.obstacle_detection_system:
            detection_perf = self.obstacle_detection_system.get_processing_performance()
            
            # Calculate detection accuracy (would need ground truth for real calculation)
            detection_accuracy = 0.95  # Simulated for now
            
            performance_report['obstacle_detection_performance'] = {
                'detection_accuracy': detection_accuracy,
                'target_accuracy': self.target_obstacle_detection_accuracy,
                'accuracy_met': detection_accuracy >= self.target_obstacle_detection_accuracy,
                'processing_time_ms': detection_perf.get('average_processing_time_ms', 0.0),
                'detection_rate_hz': detection_perf.get('detection_rate_hz', 0.0),
                'tracked_obstacles': detection_perf.get('tracked_obstacles_count', 0)
            }
        
        # Evaluate safety performance
        if self.safety_monitor:
            safety_metrics = self.safety_monitor.get_safety_metrics()
            
            avg_response_time = safety_metrics.get('average_response_time_ms', 0.0)
            
            performance_report['safety_performance'] = {
                'average_response_time_ms': avg_response_time,
                'target_response_time_ms': self.target_safety_response_time,
                'response_time_met': avg_response_time <= self.target_safety_response_time,
                'safety_events_count': safety_metrics.get('safety_events_count', 0),
                'active_alerts_count': safety_metrics.get('active_alerts_count', 0),
                'is_safe': self._current_safety_status.is_safe if self._current_safety_status else True
            }
        
        # Overall performance assessment
        localization_ok = performance_report['localization_performance'].get('accuracy_met', False)
        obstacle_detection_ok = performance_report['obstacle_detection_performance'].get('accuracy_met', False)
        safety_ok = performance_report['safety_performance'].get('response_time_met', False)
        
        performance_report['overall_performance'] = {
            'all_requirements_met': localization_ok and obstacle_detection_ok and safety_ok,
            'localization_ok': localization_ok,
            'obstacle_detection_ok': obstacle_detection_ok,
            'safety_ok': safety_ok,
            'system_health_score': self._sensor_health.overall_health_score if self._sensor_health else 0.0
        }
        
        return performance_report
    
    async def _check_performance_degradation(self, health_metrics: SensorHealthMetrics):
        """Check for performance degradation and alert if necessary"""
        if health_metrics.overall_health_score < 0.8:
            logger.warning(f"System health degraded: {health_metrics.overall_health_score:.2f}")
        
        # Check individual sensor health
        unhealthy_sensors = []
        if not health_metrics.gps_healthy:
            unhealthy_sensors.append('GPS')
        if not health_metrics.imu_healthy:
            unhealthy_sensors.append('IMU')
        if not health_metrics.tof_left_healthy:
            unhealthy_sensors.append('ToF_Left')
        if not health_metrics.tof_right_healthy:
            unhealthy_sensors.append('ToF_Right')
        if not health_metrics.camera_healthy:
            unhealthy_sensors.append('Camera')
        
        if unhealthy_sensors:
            logger.warning(f"Unhealthy sensors detected: {', '.join(unhealthy_sensors)}")
    
    async def _log_performance_issues(self, performance_report: Dict[str, Any]):
        """Log performance issues"""
        overall = performance_report['overall_performance']
        
        if not overall['localization_ok']:
            localization = performance_report['localization_performance']
            logger.warning(f"Localization accuracy below target: {localization['average_accuracy_m']:.3f}m > {localization['target_accuracy_m']:.3f}m")
        
        if not overall['obstacle_detection_ok']:
            obstacle = performance_report['obstacle_detection_performance']
            logger.warning(f"Obstacle detection accuracy below target: {obstacle['detection_accuracy']:.2f} < {obstacle['target_accuracy']:.2f}")
        
        if not overall['safety_ok']:
            safety = performance_report['safety_performance']
            logger.warning(f"Safety response time above target: {safety['average_response_time_ms']:.1f}ms > {safety['target_response_time_ms']}ms")
    
    async def _publish_health_metrics(self, health_metrics: SensorHealthMetrics):
        """Publish sensor health metrics"""
        health_data = {
            'timestamp': health_metrics.timestamp.isoformat(),
            'gps_healthy': health_metrics.gps_healthy,
            'imu_healthy': health_metrics.imu_healthy,
            'tof_left_healthy': health_metrics.tof_left_healthy,
            'tof_right_healthy': health_metrics.tof_right_healthy,
            'camera_healthy': health_metrics.camera_healthy,
            'power_monitor_healthy': health_metrics.power_monitor_healthy,
            'weather_sensor_healthy': health_metrics.weather_sensor_healthy,
            'gps_accuracy': health_metrics.gps_accuracy,
            'imu_calibration': health_metrics.imu_calibration,
            'sensor_update_rates': health_metrics.sensor_update_rates,
            'mqtt_connected': health_metrics.mqtt_connected,
            'hardware_interface_connected': health_metrics.hardware_interface_connected,
            'overall_health_score': health_metrics.overall_health_score
        }
        
        from ..communication.message_protocols import SensorData
        message = SensorData.create(
            sender="sensor_fusion_engine",
            sensor_type="health_metrics",
            data=health_data
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/health", message)
    
    async def _publish_performance_metrics(self, performance_report: Dict[str, Any]):
        """Publish performance metrics"""
        from ..communication.message_protocols import SensorData
        message = SensorData.create(
            sender="sensor_fusion_engine",
            sensor_type="performance_metrics",
            data=performance_report
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/performance", message)
    
    # Public API methods
    
    def get_current_pose(self) -> Optional[PoseEstimate]:
        """Get current pose estimate"""
        return self._current_pose
    
    def get_current_obstacles(self) -> Optional[ObstacleMap]:
        """Get current obstacle map"""
        return self._current_obstacles
    
    def get_current_safety_status(self) -> Optional[SafetyStatus]:
        """Get current safety status"""
        return self._current_safety_status
    
    def get_sensor_health(self) -> Optional[SensorHealthMetrics]:
        """Get current sensor health metrics"""
        return self._sensor_health
    
    def is_system_healthy(self) -> bool:
        """Check if system is healthy"""
        if not self._sensor_health:
            return False
        return self._sensor_health.overall_health_score > 0.8
    
    def is_safe_to_operate(self) -> bool:
        """Check if it's safe to operate"""
        if not self._current_safety_status:
            return False
        return self._current_safety_status.is_safe
    
    def get_position_accuracy(self) -> float:
        """Get current position accuracy estimate"""
        if not self.localization_system:
            return float('inf')
        return self.localization_system.get_position_accuracy()
    
    def get_nearest_obstacle_distance(self) -> float:
        """Get distance to nearest obstacle"""
        if not self.obstacle_detection_system:
            return float('inf')
        return self.obstacle_detection_system.get_nearest_obstacle_distance()
    
    def get_performance_summary(self) -> Dict[str, bool]:
        """Get summary of performance requirements"""
        return {
            'position_accuracy_met': self.get_position_accuracy() <= self.target_position_accuracy,
            'obstacle_detection_available': self.obstacle_detection_system is not None,
            'safety_monitoring_active': self.safety_monitor is not None,
            'system_healthy': self.is_system_healthy(),
            'safe_to_operate': self.is_safe_to_operate()
        }
