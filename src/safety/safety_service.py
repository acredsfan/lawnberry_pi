"""
Enhanced Comprehensive Safety Monitoring Service
Integrates all safety components with tiered access control and advanced sensor fusion
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..communication import MQTTClient, MessageProtocol, SensorData
from ..sensor_fusion.safety_monitor import SafetyMonitor
from ..sensor_fusion.data_structures import SafetyStatus, HazardAlert, HazardLevel
from ..hardware.data_structures import GPSReading
from .emergency_controller import EmergencyController
from .hazard_detector import HazardDetector
from .boundary_monitor import BoundaryMonitor
from .access_control import SafetyAccessController, SafetyAccessLevel
from .sensor_fusion_safety import SensorFusionSafetySystem
from .enhanced_protocols import EnhancedSafetyProtocols
from .environmental_safety import EnvironmentalSafetySystem
from .maintenance_safety import MaintenanceSafetySystem

logger = logging.getLogger(__name__)


@dataclass
class SafetyConfig:
    """Enhanced safety service configuration with tiered access support"""
    emergency_response_time_ms: int = 100
    safety_update_rate_hz: int = 20
    emergency_update_rate_hz: int = 50
    # New: limit how often comprehensive safety status is published to MQTT
    status_publish_rate_hz: int = 2
    person_safety_radius_m: float = 3.0
    pet_safety_radius_m: float = 1.5
    general_safety_distance_m: float = 0.3
    emergency_stop_distance_m: float = 0.15
    max_safe_tilt_deg: float = 15.0
    critical_tilt_deg: float = 25.0
    min_operating_temp_c: float = 5.0
    max_operating_temp_c: float = 40.0
    boundary_safety_margin_m: float = 1.0
    enable_weather_safety: bool = True
    enable_vision_safety: bool = True
    enable_boundary_enforcement: bool = True
    
    # Enhanced safety features
    enable_tiered_access_control: bool = True
    enable_sensor_fusion_safety: bool = True
    enable_enhanced_protocols: bool = True
    enable_environmental_safety: bool = True
    enable_maintenance_safety: bool = True
    
    # Sensor fusion parameters
    sensor_fusion_confidence_threshold: float = 0.7
    sensor_fusion_agreement_threshold: float = 0.6
    adaptive_sensor_weights: bool = True
    
    # Environmental safety parameters
    max_safe_slope_degrees: float = 15.0
    caution_slope_degrees: float = 10.0
    min_grip_factor: float = 0.6
    min_stability_factor: float = 0.7
    
    # Maintenance safety parameters
    blade_wear_threshold: float = 70.0
    battery_capacity_threshold: float = 80.0
    battery_temp_max: float = 45.0
    vibration_threshold: float = 2.0


class SafetyService:
    """
    Enhanced comprehensive safety monitoring service with tiered access control,
    advanced sensor fusion, and comprehensive safety protocols
    """
    
    def __init__(self, mqtt_client: MQTTClient, config: SafetyConfig = None):
        self.mqtt_client = mqtt_client
        self.config = config or SafetyConfig()
        
        # Core safety components
        self.safety_monitor = SafetyMonitor(mqtt_client)
        self.emergency_controller = EmergencyController(mqtt_client, self.config)
        self.hazard_detector = HazardDetector(mqtt_client, self.config)
        self.boundary_monitor = BoundaryMonitor(mqtt_client, self.config)
        
        # Enhanced safety components
        self.access_controller: Optional[SafetyAccessController] = None
        self.sensor_fusion_safety: Optional[SensorFusionSafetySystem] = None
        self.enhanced_protocols: Optional[EnhancedSafetyProtocols] = None
        self.environmental_safety: Optional[EnvironmentalSafetySystem] = None
        self.maintenance_safety: Optional[MaintenanceSafetySystem] = None
        
        # Initialize enhanced components if enabled
        self._initialize_enhanced_components()
        
        # Service state
        self._running = False
        self._service_task: Optional[asyncio.Task] = None
        self._emergency_task: Optional[asyncio.Task] = None
        
        # Current system state
        self._current_position: Optional[GPSReading] = None
        self._current_safety_status: Optional[SafetyStatus] = None
        self._system_state = "INITIALIZING"  # INITIALIZING, READY, MOWING, EMERGENCY, SHUTDOWN
        
        # Performance tracking
        self._safety_events_log: List[Dict[str, Any]] = []
        self._response_times: List[float] = []
        self._false_positive_count = 0
        self._false_negative_count = 0
        # Publish throttling
        self._last_status_publish: datetime = datetime.min
        
        # Emergency callbacks
        self._emergency_callbacks: List[Callable] = []
        
        # Enhanced safety metrics
        self._access_control_events: List[Dict[str, Any]] = []
        self._sensor_fusion_performance: Dict[str, float] = {}
        self._environmental_safety_events: List[Dict[str, Any]] = []
        self._maintenance_safety_events: List[Dict[str, Any]] = []

    def _alert_to_dict(self, alert: HazardAlert) -> Dict[str, Any]:
        """Convert a HazardAlert to a plain dict suitable for publishing/aggregation."""
        try:
            return {
                'alert_id': getattr(alert, 'alert_id', None),
                'hazard_level': getattr(getattr(alert, 'hazard_level', None), 'value', getattr(alert, 'hazard_level', 'UNKNOWN')),
                'hazard_type': getattr(alert, 'hazard_type', 'unknown'),
                'timestamp': (getattr(alert, 'timestamp').isoformat() if getattr(alert, 'timestamp', None) else datetime.now().isoformat()),
                'description': getattr(alert, 'description', ''),
                'location': getattr(alert, 'location', None),
                'sensor_data': getattr(alert, 'sensor_data', {}) or {},
                'recommended_action': getattr(alert, 'recommended_action', 'CAUTION'),
                'immediate_response_required': getattr(alert, 'immediate_response_required', False),
            }
        except Exception:
            return {'hazard_level': 'UNKNOWN', 'hazard_type': 'unknown', 'timestamp': datetime.now().isoformat()}

    def _safety_status_to_dict(self, status: SafetyStatus) -> Dict[str, Any]:
        """Convert SafetyStatus dataclass to a dict for uniform aggregation."""
        try:
            return {
                'is_safe': status.is_safe,
                'safety_level': getattr(status.safety_level, 'value', status.safety_level),
                'tilt_safe': status.tilt_safe,
                'drop_safe': status.drop_safe,
                'collision_safe': status.collision_safe,
                'weather_safe': status.weather_safe,
                'boundary_safe': status.boundary_safe,
                'tilt_angle': status.tilt_angle,
                'ground_clearance': status.ground_clearance,
                'nearest_obstacle_distance': status.nearest_obstacle_distance,
                'temperature': status.temperature,
                'humidity': status.humidity,
                'is_raining': status.is_raining,
                'active_alerts': [self._alert_to_dict(a) for a in (status.active_alerts or [])],
            }
        except Exception:
            return {'is_safe': False, 'safety_level': 'CRITICAL', 'active_alerts': []}
    
    def _initialize_enhanced_components(self):
        """Initialize enhanced safety components based on configuration"""
        try:
            # Initialize access controller
            if self.config.enable_tiered_access_control:
                self.access_controller = SafetyAccessController()
                logger.info("Initialized tiered access control system")
            
            # Initialize sensor fusion safety
            if self.config.enable_sensor_fusion_safety:
                fusion_config = {
                    'confidence_threshold': self.config.sensor_fusion_confidence_threshold,
                    'agreement_threshold': self.config.sensor_fusion_agreement_threshold,
                    'adaptive_weights': self.config.adaptive_sensor_weights
                }
                self.sensor_fusion_safety = SensorFusionSafetySystem(self.mqtt_client, fusion_config)
                logger.info("Initialized advanced sensor fusion safety system")
            
            # Initialize enhanced protocols
            if self.config.enable_enhanced_protocols and self.access_controller:
                protocols_config = {
                    'emergency_contacts': [],  # Would be loaded from config file
                    'remote_shutdown_tokens': []  # Would be loaded from secure config
                }
                self.enhanced_protocols = EnhancedSafetyProtocols(
                    self.mqtt_client, self.access_controller, protocols_config
                )
                logger.info("Initialized enhanced safety protocols")
            
            # Initialize environmental safety
            if self.config.enable_environmental_safety and self.sensor_fusion_safety:
                env_config = {
                    'max_safe_slope_degrees': self.config.max_safe_slope_degrees,
                    'caution_slope_degrees': self.config.caution_slope_degrees,
                    'min_grip_factor': self.config.min_grip_factor,
                    'min_stability_factor': self.config.min_stability_factor
                }
                self.environmental_safety = EnvironmentalSafetySystem(
                    self.mqtt_client, self.sensor_fusion_safety, env_config
                )
                logger.info("Initialized environmental safety system")
            
            # Initialize maintenance safety
            if self.config.enable_maintenance_safety and self.access_controller:
                maintenance_config = {
                    'blade_wear_threshold': self.config.blade_wear_threshold,
                    'battery_capacity_threshold': self.config.battery_capacity_threshold,
                    'battery_temp_max': self.config.battery_temp_max,
                    'vibration_threshold': self.config.vibration_threshold
                }
                self.maintenance_safety = MaintenanceSafetySystem(
                    self.mqtt_client, self.access_controller, maintenance_config
                )
                logger.info("Initialized maintenance safety system")
            
        except Exception as e:
            logger.error(f"Failed to initialize enhanced safety components: {e}")
            raise
        
    async def start(self):
        """Start the enhanced comprehensive safety service"""
        logger.info("Starting enhanced comprehensive safety monitoring service")
        self._running = True
        
        # Subscribe to system commands
        await self._subscribe_to_commands()
        
        # Start core safety components
        await self.safety_monitor.start()
        await self.emergency_controller.start()
        await self.hazard_detector.start()
        if self.config.enable_boundary_enforcement:
            await self.boundary_monitor.start()
        
        # Start enhanced safety components
        await self._start_enhanced_components()
        
        # Register emergency callbacks between components
        self.safety_monitor.register_emergency_callback(self._handle_safety_emergency)
        self.hazard_detector.register_emergency_callback(self._handle_hazard_emergency)
        self.boundary_monitor.register_emergency_callback(self._handle_boundary_emergency)
        
        # Register enhanced safety callbacks
        await self._register_enhanced_callbacks()
        
        # Start service coordination tasks
        self._service_task = asyncio.create_task(self._safety_coordination_loop())
        self._emergency_task = asyncio.create_task(self._emergency_coordination_loop())
        
        logger.info("Enhanced safety monitoring service started successfully")
    
    async def _start_enhanced_components(self):
        """Start enhanced safety components"""
        try:
            if self.sensor_fusion_safety:
                await self.sensor_fusion_safety.start()
                logger.debug("Started sensor fusion safety system")
            
            if self.enhanced_protocols:
                await self.enhanced_protocols.start()
                logger.debug("Started enhanced safety protocols")
            
            if self.environmental_safety:
                await self.environmental_safety.start()
                logger.debug("Started environmental safety system")
            
            if self.maintenance_safety:
                await self.maintenance_safety.start()
                logger.debug("Started maintenance safety system")
                
        except Exception as e:
            logger.error(f"Failed to start enhanced safety components: {e}")
            raise
    
    async def _register_enhanced_callbacks(self):
        """Register callbacks for enhanced safety components"""
        try:
            # Register sensor fusion callbacks
            if self.sensor_fusion_safety:
                self.sensor_fusion_safety.register_obstacle_callback(self._handle_sensor_fusion_obstacle)
                self.sensor_fusion_safety.register_environmental_callback(self._handle_environmental_change)
            
            # Register enhanced protocol callbacks
            if self.enhanced_protocols:
                self.enhanced_protocols.register_violation_callback(self._handle_safety_violation)
                self.enhanced_protocols.register_emergency_callback(self._handle_enhanced_emergency)
            
            # Register environmental safety callbacks
            if self.environmental_safety:
                self.environmental_safety.register_slope_callback(self._handle_slope_analysis)
                self.environmental_safety.register_surface_callback(self._handle_surface_analysis)
                self.environmental_safety.register_wildlife_callback(self._handle_wildlife_detection)
                self.environmental_safety.register_hazard_callback(self._handle_environmental_hazard)
            
            # Register maintenance safety callbacks
            if self.maintenance_safety:
                self.maintenance_safety.register_blade_callback(self._handle_blade_analysis)
                self.maintenance_safety.register_battery_callback(self._handle_battery_analysis)
                self.maintenance_safety.register_lockout_callback(self._handle_maintenance_lockout)
                self.maintenance_safety.register_diagnostic_callback(self._handle_diagnostic_result)
                
        except Exception as e:
            logger.error(f"Failed to register enhanced safety callbacks: {e}")
        
        # Subscribe to position updates and system state using correct client API
        try:
            gps_topic = "lawnberry/sensors/gps/data"
            await self.mqtt_client.subscribe(gps_topic)
            self.mqtt_client.add_message_handler(gps_topic, self._handle_position_update)
        except Exception as e:
            logger.error(f"Failed to subscribe to GPS topic: {e}")
        try:
            state_topic = "lawnberry/system/state"
            await self.mqtt_client.subscribe(state_topic)
            self.mqtt_client.add_message_handler(state_topic, self._handle_system_state_change)
        except Exception as e:
            logger.error(f"Failed to subscribe to system state topic: {e}")
        
        logger.info("Enhanced safety service started successfully")
    
    async def _stop_enhanced_components(self):
        """Stop enhanced safety components"""
        try:
            if self.maintenance_safety:
                await self.maintenance_safety.stop()
                logger.debug("Stopped maintenance safety system")
            
            if self.environmental_safety:
                await self.environmental_safety.stop()
                logger.debug("Stopped environmental safety system")
            
            if self.enhanced_protocols:
                await self.enhanced_protocols.stop()
                logger.debug("Stopped enhanced safety protocols")
            
            if self.sensor_fusion_safety:
                await self.sensor_fusion_safety.stop()
                logger.debug("Stopped sensor fusion safety system")
                
        except Exception as e:
            logger.error(f"Error stopping enhanced safety components: {e}")
    
    # Enhanced safety callback handlers
    async def _handle_sensor_fusion_obstacle(self, obstacle):
        """Handle sensor fusion obstacle detection"""
        self._sensor_fusion_performance['obstacles_detected'] = self._sensor_fusion_performance.get('obstacles_detected', 0) + 1
        
        # Trigger emergency response for critical obstacles
        if obstacle.threat_level.value in ['CRITICAL', 'HIGH']:
            await self._trigger_emergency_response({
                'type': 'sensor_fusion_obstacle',
                'obstacle_id': obstacle.obstacle_id,
                'threat_level': obstacle.threat_level.value,
                'position': obstacle.position,
                'confidence': obstacle.confidence
            })
        
        logger.debug(f"Sensor fusion obstacle detected: {obstacle.classification} at {obstacle.position}")
    
    async def _handle_environmental_change(self, conditions):
        """Handle environmental condition changes"""
        # Log environmental changes that might affect safety
        logger.debug(f"Environmental conditions updated: temp={conditions.temperature}°C, visibility={conditions.visibility_factor}")
    
    async def _handle_safety_violation(self, event):
        """Handle safety violation from enhanced protocols"""
        self._access_control_events.append({
            'event_id': event.event_id,
            'type': event.event_type.value,
            'severity': event.severity.value,
            'timestamp': event.timestamp,
            'user': event.user_involved
        })
        
        # Trigger emergency response for critical violations
        if event.severity.value in ['EMERGENCY_STOP', 'SYSTEM_SHUTDOWN']:
            await self._trigger_emergency_response({
                'type': 'safety_violation',
                'event_id': event.event_id,
                'description': event.description,
                'severity': event.severity.value
            })
        
        logger.warning(f"Safety violation: {event.description}")
    
    async def _handle_enhanced_emergency(self, event):
        """Handle enhanced emergency events"""
        await self._trigger_emergency_response({
            'type': 'enhanced_emergency',
            'event_id': event.event_id,
            'description': event.description,
            'severity': event.severity.value
        })
        
        logger.critical(f"Enhanced emergency: {event.description}")
    
    async def _handle_slope_analysis(self, analysis):
        """Handle slope analysis results"""
        if analysis.safety_assessment.value in ['UNSAFE', 'PROHIBITED']:
            self._environmental_safety_events.append({
                'type': 'unsafe_slope',
                'angle': analysis.angle_degrees,
                'assessment': analysis.safety_assessment.value,
                'timestamp': datetime.now()
            })
            
            logger.warning(f"Unsafe slope detected: {analysis.angle_degrees:.1f}° - {analysis.safety_assessment.value}")
    
    async def _handle_surface_analysis(self, analysis):
        """Handle surface analysis results"""
        if analysis.mowing_suitability < 0.3:
            self._environmental_safety_events.append({
                'type': 'unsuitable_surface',
                'surface_type': analysis.surface_type.value,
                'suitability': analysis.mowing_suitability,
                'timestamp': datetime.now()
            })
            
            logger.warning(f"Unsuitable surface: {analysis.surface_type.value} (suitability: {analysis.mowing_suitability:.2f})")
    
    async def _handle_wildlife_detection(self, detection):
        """Handle wildlife detection"""
        if detection.threat_level > 0.7:
            self._environmental_safety_events.append({
                'type': 'wildlife_threat',
                'wildlife_type': detection.wildlife_type.value,
                'threat_level': detection.threat_level,
                'position': detection.position,
                'timestamp': detection.timestamp
            })
            
            logger.warning(f"Wildlife threat: {detection.wildlife_type.value} (threat: {detection.threat_level:.2f})")
    
    async def _handle_environmental_hazard(self, hazard):
        """Handle environmental hazards"""
        if hazard.severity > 0.8:
            await self._trigger_emergency_response({
                'type': 'environmental_hazard',
                'hazard_id': hazard.hazard_id,
                'hazard_type': hazard.hazard_type,
                'severity': hazard.severity,
                'action': hazard.recommended_action
            })
        
        logger.warning(f"Environmental hazard: {hazard.hazard_type} (severity: {hazard.severity:.2f})")
    
    async def _handle_blade_analysis(self, blade_data):
        """Handle blade wear analysis"""
        if blade_data.safety_concern:
            self._maintenance_safety_events.append({
                'type': 'blade_safety_concern',
                'blade_id': blade_data.blade_id,
                'condition': blade_data.condition.value,
                'wear_percentage': blade_data.wear_percentage,
                'timestamp': blade_data.timestamp
            })
            
            logger.warning(f"Blade safety concern: {blade_data.condition.value} ({blade_data.wear_percentage:.1f}% wear)")
    
    async def _handle_battery_analysis(self, battery_data):
        """Handle battery health analysis"""
        if battery_data.safety_concerns:
            self._maintenance_safety_events.append({
                'type': 'battery_safety_concern',
                'battery_id': battery_data.battery_id,
                'concerns': battery_data.safety_concerns,
                'capacity': battery_data.capacity_percentage,
                'timestamp': battery_data.timestamp
            })
            
            logger.warning(f"Battery safety concerns: {', '.join(battery_data.safety_concerns)}")
    
    async def _handle_maintenance_lockout(self, lockout):
        """Handle maintenance lockout"""
        if lockout.severity.value == 'CRITICAL':
            await self._trigger_emergency_response({
                'type': 'maintenance_lockout',
                'lockout_id': lockout.lockout_id,
                'description': lockout.description,
                'affected_systems': lockout.affected_systems
            })
        
        logger.warning(f"Maintenance lockout: {lockout.description}")
    
    async def _handle_diagnostic_result(self, diagnostic):
        """Handle diagnostic results"""
        if diagnostic.safety_impact and diagnostic.status.value == 'CRITICAL':
            self._maintenance_safety_events.append({
                'type': 'diagnostic_failure',
                'test_name': diagnostic.test_name,
                'status': diagnostic.status.value,
                'issues': diagnostic.issues_found,
                'timestamp': diagnostic.timestamp
            })
            
            logger.warning(f"Critical diagnostic failure: {diagnostic.test_name}")
    
    async def _trigger_emergency_response(self, event_data):
        """Trigger emergency response for enhanced safety events"""
        # Publish emergency event on namespaced topic
        await self.mqtt_client.publish("lawnberry/safety/emergency", event_data)
        
        # Trigger emergency callbacks
        for callback in self._emergency_callbacks:
            try:
                await callback(event_data)
            except Exception as e:
                logger.error(f"Error in emergency callback: {e}")
        
        # Update safety status to emergency
        self._system_state = "EMERGENCY"
        self._safety_events_log.append({
            'timestamp': datetime.now(),
            'event_type': 'emergency_response',
            'data': event_data
        })
    
    async def get_enhanced_safety_status(self):
        """Get comprehensive enhanced safety status"""
        base_status = await self.get_comprehensive_safety_status()
        
        enhanced_status = {
            'access_control': {
                'enabled': self.access_controller is not None,
                'total_events': len(self._access_control_events),
                'recent_events': len([e for e in self._access_control_events if (datetime.now() - e['timestamp']).seconds < 3600])
            },
            'sensor_fusion': {
                'enabled': self.sensor_fusion_safety is not None,
                'performance_metrics': self._sensor_fusion_performance,
                'system_status': await self.sensor_fusion_safety.get_system_status() if self.sensor_fusion_safety else None
            },
            'enhanced_protocols': {
                'enabled': self.enhanced_protocols is not None,
                'safety_status': await self.enhanced_protocols.get_safety_status() if self.enhanced_protocols else None
            },
            'environmental_safety': {
                'enabled': self.environmental_safety is not None,
                'total_events': len(self._environmental_safety_events),
                'status': await self.environmental_safety.get_environmental_status() if self.environmental_safety else None
            },
            'maintenance_safety': {
                'enabled': self.maintenance_safety is not None,
                'total_events': len(self._maintenance_safety_events),
                'status': await self.maintenance_safety.get_maintenance_status() if self.maintenance_safety else None
            }
        }
        
        # Merge with base status
        base_status.update({'enhanced_features': enhanced_status})
        return base_status
    
    # User access control methods
    async def register_user(self, username: str, initial_level: SafetyAccessLevel = SafetyAccessLevel.BASIC):
        """Register a user in the safety access control system"""
        if self.access_controller:
            return await self.access_controller.register_user(username, initial_level)
        return False
    
    async def check_user_access(self, username: str, parameter: str = None, feature: str = None):
        """Check user access to safety parameters or features"""
        if not self.access_controller:
            return True  # Default to allow if access control disabled
        
        if parameter:
            return await self.access_controller.check_parameter_access(username, parameter)
        elif feature:
            return await self.access_controller.check_feature_access(username, feature)
        
        return False
    
    async def complete_safety_training(self, username: str, module: str, score: float):
        """Record safety training completion"""
        if self.access_controller:
            from .access_control import TrainingModule
            try:
                training_module = TrainingModule(module)
                return await self.access_controller.complete_training(username, training_module, score)
            except ValueError:
                logger.error(f"Invalid training module: {module}")
                return False
        return False

    async def stop(self):
        """Stop the enhanced comprehensive safety service"""
        logger.info("Stopping enhanced comprehensive safety monitoring service")
        self._running = False
        
        # Cancel service tasks
        if self._service_task:
            self._service_task.cancel()
            try:
                await self._service_task
            except asyncio.CancelledError:
                pass
                
        if self._emergency_task:
            self._emergency_task.cancel()
            try:
                await self._emergency_task
            except asyncio.CancelledError:
                pass
        
        # Stop enhanced safety components
        await self._stop_enhanced_components()
        
        # Stop core safety components
        await self.boundary_monitor.stop()
        await self.hazard_detector.stop()
        await self.emergency_controller.stop()
        await self.safety_monitor.stop()
        
        logger.info("Enhanced comprehensive safety monitoring service stopped")
    
    async def _subscribe_to_commands(self):
        """Subscribe to safety-related commands"""
        try:
            topic = "lawnberry/safety/emergency_stop"
            await self.mqtt_client.subscribe(topic)
            self.mqtt_client.add_message_handler(topic, self._handle_emergency_stop_command)
        except Exception as e:
            logger.error(f"Failed to subscribe to {topic}: {e}")
        try:
            topic = "lawnberry/commands/emergency"
            await self.mqtt_client.subscribe(topic)
            self.mqtt_client.add_message_handler(topic, self._handle_emergency_command)
        except Exception as e:
            logger.error(f"Failed to subscribe to {topic}: {e}")
        try:
            topic = "lawnberry/safety/test"
            await self.mqtt_client.subscribe(topic)
            self.mqtt_client.add_message_handler(topic, self._handle_safety_test)
        except Exception as e:
            logger.error(f"Failed to subscribe to {topic}: {e}")
    
    async def _handle_emergency_stop_command(self, topic: str, message):
        """Handle external emergency stop command"""
        try:
            command_data = message.payload if hasattr(message, 'payload') else (message if isinstance(message, dict) else {})
            reason = command_data.get('reason', 'External emergency stop command')
            triggered_by = command_data.get('triggered_by', 'unknown')
            
            logger.critical(f"Emergency stop commanded by {triggered_by}: {reason}")
            
            # Trigger immediate emergency response
            await self.trigger_emergency_stop(reason=reason, triggered_by=triggered_by)
            
        except Exception as e:
            logger.error(f"Error handling emergency stop command: {e}")
    
    async def _handle_emergency_command(self, topic: str, message):
        """Handle emergency commands"""
        try:
            command_data = message.payload if hasattr(message, 'payload') else (message if isinstance(message, dict) else {})
            command = command_data.get('command')
            
            if command == 'emergency_stop':
                await self._handle_emergency_stop_command(topic, message)
            elif command == 'safety_override':
                await self._handle_safety_override(command_data)
            elif command == 'reset_safety':
                await self._handle_safety_reset(command_data)
            
        except Exception as e:
            logger.error(f"Error handling emergency command: {e}")
    
    async def _handle_position_update(self, topic: str, message):
        """Handle GPS position updates for boundary monitoring"""
        try:
            if hasattr(message, 'payload'):
                gps_data = message.payload
                ts = getattr(message, 'metadata', None).timestamp if getattr(message, 'metadata', None) else None
            else:
                gps_data = message if isinstance(message, dict) else {}
                ts = None
            self._current_position = GPSReading(
                timestamp=datetime.fromtimestamp(ts) if ts else datetime.now(),
                sensor_id=gps_data.get('sensor_id', 'gps'),
                value=gps_data,
                unit='degrees',
                latitude=gps_data['latitude'],
                longitude=gps_data['longitude'],
                altitude=gps_data.get('altitude', 0.0),
                accuracy=gps_data.get('accuracy', 10.0),
                satellites=gps_data.get('satellites', 0)
            )
            
            # Update boundary monitor with current position
            if self.config.enable_boundary_enforcement:
                await self.boundary_monitor.update_position(self._current_position)
                
        except Exception as e:
            logger.error(f"Error handling position update: {e}")
    
    async def _handle_system_state_change(self, topic: str, message):
        """Handle system state changes"""
        try:
            state_data = message.payload if hasattr(message, 'payload') else (message if isinstance(message, dict) else {})
            new_state = state_data.get('state', 'UNKNOWN')
            
            if new_state != self._system_state:
                logger.info(f"System state changed: {self._system_state} -> {new_state}")
                self._system_state = new_state
                
                # Adjust safety monitoring based on state
                await self._adjust_safety_monitoring_for_state(new_state)
                
        except Exception as e:
            logger.error(f"Error handling system state change: {e}")
    
    async def _safety_coordination_loop(self):
        """Main safety coordination loop"""
        loop_interval = 1.0 / self.config.safety_update_rate_hz
        
        while self._running:
            try:
                start_time = datetime.now()
                
                # Collect safety status from all components
                safety_status = await self._collect_comprehensive_safety_status()
                self._current_safety_status = safety_status
                
                # Analyze and coordinate safety responses
                await self._coordinate_safety_response(safety_status)
                
                # Publish comprehensive safety status (throttled)
                now = datetime.now()
                min_publish_interval = 1.0 / max(1, int(self.config.status_publish_rate_hz))
                if (now - self._last_status_publish).total_seconds() >= min_publish_interval:
                    await self._publish_comprehensive_safety_status(safety_status)
                    self._last_status_publish = now
                
                # Log safety events
                await self._log_safety_events(safety_status)
                
                # Calculate loop performance
                loop_time = (datetime.now() - start_time).total_seconds()
                if loop_time > loop_interval:
                    logger.warning(f"Safety coordination loop took {loop_time*1000:.1f}ms (target: {loop_interval*1000:.1f}ms)")
                
                await asyncio.sleep(max(0, loop_interval - loop_time))
                
            except Exception as e:
                logger.error(f"Error in safety coordination loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _emergency_coordination_loop(self):
        """Ultra-fast emergency coordination loop"""
        loop_interval = 1.0 / self.config.emergency_update_rate_hz
        
        while self._running:
            try:
                start_time = datetime.now()
                
                # Check for critical emergency conditions across all components
                critical_hazards = await self._check_critical_emergency_conditions()
                
                if critical_hazards:
                    # Trigger coordinated emergency response
                    await self._trigger_coordinated_emergency_response(critical_hazards)
                
                # Monitor emergency response performance
                loop_time = (datetime.now() - start_time).total_seconds()
                response_time_ms = loop_time * 1000
                
                if response_time_ms > self.config.emergency_response_time_ms:
                    logger.warning(f"Emergency loop took {response_time_ms:.1f}ms (target: {self.config.emergency_response_time_ms}ms)")
                
                self._response_times.append(response_time_ms)
                if len(self._response_times) > 100:  # Keep last 100 measurements
                    self._response_times.pop(0)
                
                await asyncio.sleep(max(0, loop_interval - loop_time))
                
            except Exception as e:
                logger.error(f"Error in emergency coordination loop: {e}")
                await asyncio.sleep(0.01)

    async def _trigger_coordinated_emergency_response(self, critical_hazards: List[Dict[str, Any]]):
        """Coordinate emergency response across subsystems (minimal implementation)."""
        try:
            # Aggregate and publish a consolidated emergency event
            consolidated = {
                'timestamp': datetime.now().isoformat(),
                'source': 'safety_service',
                'hazards': critical_hazards,
            }
            await self._broadcast_emergency_alert(consolidated)

            # Execute emergency stop for critical hazards
            await self.emergency_controller.execute_emergency_stop("Coordinated emergency response")
        except Exception as e:
            logger.error(f"Error triggering coordinated emergency response: {e}")

    async def _broadcast_emergency_alert(self, alert: Dict[str, Any]):
        """Broadcast an emergency alert on standardized topic."""
        try:
            await self.mqtt_client.publish("lawnberry/safety/emergency", SensorData.create(
                sender="safety_service",
                sensor_type="emergency_broadcast",
                data=alert,
            ))
        except Exception as e:
            logger.error(f"Error broadcasting emergency alert: {e}")
    
    async def trigger_emergency_stop(self, reason: str = "Manual emergency stop", 
                                   triggered_by: str = "system") -> bool:
        """Trigger comprehensive emergency stop"""
        try:
            start_time = datetime.now()
            logger.critical(f"EMERGENCY STOP TRIGGERED: {reason} (by: {triggered_by})")
            
            # Create emergency alert
            emergency_alert = {
                'alert_id': f"emergency_{int(datetime.now().timestamp())}",
                'hazard_level': 'CRITICAL',
                'hazard_type': 'emergency_stop',
                'timestamp': start_time.isoformat(),
                'description': reason,
                'triggered_by': triggered_by,
                'immediate_response_required': True
            }
            
            # Execute emergency stop across all components
            emergency_tasks = [
                self.emergency_controller.execute_emergency_stop(reason),
                self.safety_monitor._trigger_emergency_response([emergency_alert]),
                self._broadcast_emergency_alert(emergency_alert)
            ]
            
            # Wait for all emergency responses
            await asyncio.gather(*emergency_tasks, return_exceptions=True)
            
            # Calculate response time
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log emergency event
            emergency_event = {
                'timestamp': start_time.isoformat(),
                'event_type': 'emergency_stop',
                'reason': reason,
                'triggered_by': triggered_by,
                'response_time_ms': response_time_ms,
                'success': response_time_ms <= self.config.emergency_response_time_ms
            }
            self._safety_events_log.append(emergency_event)
            
            logger.critical(f"Emergency stop completed in {response_time_ms:.1f}ms")
            return response_time_ms <= self.config.emergency_response_time_ms
            
        except Exception as e:
            logger.error(f"Error executing emergency stop: {e}")
            return False
    
    async def _collect_comprehensive_safety_status(self) -> Dict[str, Any]:
        """Collect comprehensive safety status from all components"""
        try:
            # Helper: normalize component status into a dict with 'is_safe' and 'active_alerts' list of dicts
            def _normalize_component_status(status_obj: Any) -> Dict[str, Any]:
                try:
                    if status_obj is None:
                        return {'is_safe': True, 'active_alerts': []}
                    if isinstance(status_obj, SafetyStatus):
                        return self._safety_status_to_dict(status_obj)
                    if isinstance(status_obj, dict):
                        # Ensure active_alerts is a list of dicts
                        alerts = status_obj.get('active_alerts', []) or []
                        normalized_alerts: List[Dict[str, Any]] = []
                        for a in alerts:
                            if isinstance(a, HazardAlert):
                                normalized_alerts.append(self._alert_to_dict(a))
                            elif isinstance(a, dict):
                                normalized_alerts.append(a)
                        status_obj['active_alerts'] = normalized_alerts
                        # Ensure is_safe key exists
                        status_obj.setdefault('is_safe', True)
                        return status_obj
                    # Unknown type; fallback safe
                    logger.debug(f"Component status type {type(status_obj)} not recognized; defaulting to safe dict")
                    return {'is_safe': True, 'active_alerts': []}
                except Exception:
                    return {'is_safe': False, 'active_alerts': []}

            # Get and normalize status from all safety components
            safety_monitor_status = _normalize_component_status(self.safety_monitor.get_current_safety_status())
            hazard_detector_status = _normalize_component_status(await self.hazard_detector.get_current_status())
            boundary_status = _normalize_component_status(
                await self.boundary_monitor.get_current_status() if self.config.enable_boundary_enforcement else None
            ) if self.config.enable_boundary_enforcement else None
            emergency_controller_status = _normalize_component_status(self.emergency_controller.get_current_status())
            
            # Snapshot types for diagnostics
            def _snapshot_component_types(mapper: Dict[str, Any]) -> Dict[str, str]:
                snap = {}
                for k, v in mapper.items():
                    snap[k] = type(v).__name__
                return snap

            # Combine into comprehensive status
            comprehensive_status = {
                'timestamp': datetime.now().isoformat(),
                'system_state': self._system_state,
                'overall_safe': True,
                'safety_level': 'NONE',
                'active_alerts': [],
                'components': {
                    'safety_monitor': safety_monitor_status,
                    'hazard_detector': hazard_detector_status,
                    'boundary_monitor': boundary_status if boundary_status is not None else {'is_safe': True, 'active_alerts': []},
                    'emergency_controller': emergency_controller_status
                },
                'performance_metrics': {
                    'average_response_time_ms': sum(self._response_times) / len(self._response_times) if self._response_times else 0.0,
                    'max_response_time_ms': max(self._response_times) if self._response_times else 0.0,
                    'safety_events_count': len(self._safety_events_log),
                    'false_positive_rate': self._false_positive_count / max(1, len(self._safety_events_log)),
                    'uptime_hours': (datetime.now() - datetime.now()).total_seconds() / 3600  # Placeholder
                }
            }
            
            # Determine overall safety status
            all_components_safe = True
            highest_alert_level = HazardLevel.NONE
            
            # Defensive pass: ensure every component status is a dict before using .get
            for component_name, component_status in list(comprehensive_status['components'].items()):
                if isinstance(component_status, SafetyStatus):
                    logger.debug(f"Normalizing SafetyStatus from component '{component_name}' to dict")
                    component_status = self._safety_status_to_dict(component_status)
                    comprehensive_status['components'][component_name] = component_status
                elif not isinstance(component_status, dict):
                    logger.debug(f"Component '{component_name}' returned non-dict status of type {type(component_status)}; coercing to default safe dict")
                    component_status = {'is_safe': True, 'active_alerts': []}
                    comprehensive_status['components'][component_name] = component_status

            for component_name, component_status in comprehensive_status['components'].items():
                # component_status is guaranteed dict by normalization above
                try:
                    if component_status and not component_status.get('is_safe', True):
                        all_components_safe = False
                    # Collect alerts from all components
                    if component_status.get('active_alerts'):
                        # Ensure per-component alerts are dicts
                        norm_alerts: List[Dict[str, Any]] = []
                        for a in component_status['active_alerts']:
                            if isinstance(a, HazardAlert):
                                norm_alerts.append(self._alert_to_dict(a))
                            elif isinstance(a, dict):
                                norm_alerts.append(a)
                        comprehensive_status['active_alerts'].extend(norm_alerts)
                except Exception as e_loop:
                    logger.error(f"Component aggregation error for '{component_name}': {e_loop} (type={type(component_status)})")
                    # Force-safe fallback for this component
                    continue
            
            comprehensive_status['overall_safe'] = all_components_safe
            
            # Determine overall safety level
            if comprehensive_status['active_alerts']:
                # Ensure alerts are dicts (defensive) before computing levels
                normalized_alerts: List[Dict[str, Any]] = []
                for a in comprehensive_status['active_alerts']:
                    if isinstance(a, HazardAlert):
                        normalized_alerts.append(self._alert_to_dict(a))
                    elif isinstance(a, dict):
                        normalized_alerts.append(a)
                comprehensive_status['active_alerts'] = normalized_alerts

                alert_levels = [alert.get('hazard_level', 'NONE') for alert in comprehensive_status['active_alerts']]
                if 'CRITICAL' in alert_levels:
                    comprehensive_status['safety_level'] = 'CRITICAL'
                elif 'HIGH' in alert_levels:
                    comprehensive_status['safety_level'] = 'HIGH'
                elif 'MEDIUM' in alert_levels:
                    comprehensive_status['safety_level'] = 'MEDIUM'
                elif 'LOW' in alert_levels:
                    comprehensive_status['safety_level'] = 'LOW'
            
            return comprehensive_status
            
        except Exception as e:
            try:
                comp_types = {}
                # Attempt to gather component type snapshot for diagnostics
                comp_map = {
                    'safety_monitor': self.safety_monitor.get_current_safety_status(),
                    'hazard_detector': await self.hazard_detector.get_current_status(),
                    'boundary_monitor': (await self.boundary_monitor.get_current_status()) if self.config.enable_boundary_enforcement else None,
                    'emergency_controller': self.emergency_controller.get_current_status()
                }
                for k, v in comp_map.items():
                    comp_types[k] = type(v).__name__
                logger.error(f"Error collecting comprehensive safety status: {e} | component types: {comp_types}")
            except Exception:
                logger.error(f"Error collecting comprehensive safety status: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_safe': False,
                'safety_level': 'CRITICAL',
                'error': str(e)
            }

    async def _coordinate_safety_response(self, safety_status: Dict[str, Any]):
        """Analyze current safety status and coordinate responses.
        Minimal implementation: if any critical alert is present, trigger emergency stop; if high, log warning.
        """
        try:
            alerts = safety_status.get('active_alerts', []) or []
            levels = {str(a.get('hazard_level', '')).upper() for a in alerts}

            if 'CRITICAL' in levels:
                await self.emergency_controller.execute_emergency_stop("Critical hazard detected")
                return

            if 'HIGH' in levels:
                logger.warning("High-level hazard detected; monitoring closely")
        except Exception as e:
            logger.error(f"Error coordinating safety response: {e}")

    async def _publish_comprehensive_safety_status(self, safety_status: Dict[str, Any]):
        """Publish the comprehensive safety status over MQTT for the UI and other services."""
        try:
            payload = SensorData.create(
                sender="safety_service",
                sensor_type="safety_status",
                data=safety_status,
            )
            await self.mqtt_client.publish("lawnberry/safety/status", payload)
        except Exception as e:
            logger.error(f"Error publishing safety status: {e}")

    async def _log_safety_events(self, safety_status: Dict[str, Any]):
        """Record significant safety events for metrics and auditing."""
        try:
            level = safety_status.get('safety_level', 'NONE')
            if level in ('HIGH', 'CRITICAL'):
                self._safety_events_log.append({
                    'timestamp': datetime.now().isoformat(),
                    'event_type': 'status_update',
                    'safety_level': level,
                    'active_alerts': len(safety_status.get('active_alerts', []) or []),
                })
                # Prevent unbounded growth
                if len(self._safety_events_log) > 1000:
                    self._safety_events_log = self._safety_events_log[-500:]
        except Exception as e:
            logger.error(f"Error logging safety events: {e}")
    
    async def _check_critical_emergency_conditions(self) -> List[Dict[str, Any]]:
        """Check for critical emergency conditions across all components"""
        critical_hazards = []
        
        try:
            # Check safety monitor for critical conditions
            safety_hazards = await self.safety_monitor._check_emergency_conditions()
            for hazard in safety_hazards:
                if hazard.hazard_level == HazardLevel.CRITICAL:
                    critical_hazards.append({
                        'source': 'safety_monitor',
                        'alert': hazard,
                        'immediate_response_required': True
                    })
            
            # Check hazard detector for critical conditions
            hazard_critical = await self.hazard_detector.check_critical_hazards()
            critical_hazards.extend(hazard_critical)
            
            # Check boundary monitor for critical violations
            if self.config.enable_boundary_enforcement:
                boundary_critical = await self.boundary_monitor.check_critical_violations()
                critical_hazards.extend(boundary_critical)
                
        except Exception as e:
            logger.error(f"Error checking critical emergency conditions: {e}")
            # Add error as critical hazard
            critical_hazards.append({
                'source': 'safety_service',
                'alert': {
                    'hazard_type': 'system_error',
                    'hazard_level': 'CRITICAL',
                    'description': f"Safety system error: {e}",
                    'immediate_response_required': True
                }
            })
        
        return critical_hazards
    
    async def get_safety_metrics(self) -> Dict[str, Any]:
        """Get comprehensive safety performance metrics"""
        return {
            'service_status': {
                'running': self._running,
                'system_state': self._system_state,
                'components_active': 4 if self.config.enable_boundary_enforcement else 3
            },
            'performance': {
                'average_response_time_ms': sum(self._response_times) / len(self._response_times) if self._response_times else 0.0,
                'max_response_time_ms': max(self._response_times) if self._response_times else 0.0,
                'target_response_time_ms': self.config.emergency_response_time_ms,
                'response_time_compliance': len([t for t in self._response_times if t <= self.config.emergency_response_time_ms]) / max(1, len(self._response_times))
            },
            'safety_events': {
                'total_events': len(self._safety_events_log),
                'emergency_stops': len([e for e in self._safety_events_log if e['event_type'] == 'emergency_stop']),
                'false_positives': self._false_positive_count,
                'false_negatives': self._false_negative_count
            },
            'component_metrics': {
                'safety_monitor': self.safety_monitor.get_safety_metrics(),
                'hazard_detector': await self.hazard_detector.get_metrics(),
                'boundary_monitor': await self.boundary_monitor.get_metrics() if self.config.enable_boundary_enforcement else None,
                'emergency_controller': self.emergency_controller.get_metrics()
            }
        }
    
    # Additional callback handlers and utility methods would continue here...
    async def _handle_safety_emergency(self, hazards: List[HazardAlert]):
        """Handle emergency from safety monitor"""
        for callback in self._emergency_callbacks:
            try:
                await callback('safety_monitor', hazards)
            except Exception as e:
                logger.error(f"Error in safety emergency callback: {e}")
    
    async def _handle_hazard_emergency(self, hazards: List[Dict[str, Any]]):
        """Handle emergency from hazard detector"""
        for callback in self._emergency_callbacks:
            try:
                await callback('hazard_detector', hazards)
            except Exception as e:
                logger.error(f"Error in hazard emergency callback: {e}")
    
    async def _handle_boundary_emergency(self, violations: List[Dict[str, Any]]):
        """Handle emergency from boundary monitor"""
        for callback in self._emergency_callbacks:
            try:
                await callback('boundary_monitor', violations)
            except Exception as e:
                logger.error(f"Error in boundary emergency callback: {e}")
    
    def register_emergency_callback(self, callback: Callable):
        """Register callback for emergency situations"""
        self._emergency_callbacks.append(callback)

    async def _handle_safety_test(self, topic: str, message):
        """Handle safety test messages and provide an acknowledgement on MQTT."""
        try:
            payload = message.payload if hasattr(message, 'payload') else (message if isinstance(message, dict) else {'raw': str(message)})
            logger.info(f"Safety test message on {topic}: {payload}")
            ack = {
                'timestamp': datetime.now().isoformat(),
                'event': 'safety_test_ack',
                'received': payload,
            }
            await self.mqtt_client.publish("lawnberry/safety/alerts/test", ack)
        except Exception as e:
            logger.error(f"Error handling safety test message: {e}")
