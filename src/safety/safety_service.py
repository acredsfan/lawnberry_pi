"""
Comprehensive Safety Monitoring Service
Integrates all safety components with 100ms emergency response
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

logger = logging.getLogger(__name__)


@dataclass
class SafetyConfig:
    """Safety service configuration"""
    emergency_response_time_ms: int = 100
    safety_update_rate_hz: int = 20
    emergency_update_rate_hz: int = 50
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


class SafetyService:
    """
    Comprehensive safety monitoring service that coordinates all safety components
    and provides 100ms emergency response capability
    """
    
    def __init__(self, mqtt_client: MQTTClient, config: SafetyConfig = None):
        self.mqtt_client = mqtt_client
        self.config = config or SafetyConfig()
        
        # Core safety components
        self.safety_monitor = SafetyMonitor(mqtt_client)
        self.emergency_controller = EmergencyController(mqtt_client, self.config)
        self.hazard_detector = HazardDetector(mqtt_client, self.config)
        self.boundary_monitor = BoundaryMonitor(mqtt_client, self.config)
        
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
        
        # Emergency callbacks
        self._emergency_callbacks: List[Callable] = []
        
    async def start(self):
        """Start the comprehensive safety service"""
        logger.info("Starting comprehensive safety monitoring service")
        self._running = True
        
        # Subscribe to system commands
        await self._subscribe_to_commands()
        
        # Start all safety components
        await self.safety_monitor.start()
        await self.emergency_controller.start()
        await self.hazard_detector.start()
        if self.config.enable_boundary_enforcement:
            await self.boundary_monitor.start()
        
        # Register emergency callbacks between components
        self.safety_monitor.register_emergency_callback(self._handle_safety_emergency)
        self.hazard_detector.register_emergency_callback(self._handle_hazard_emergency)
        self.boundary_monitor.register_emergency_callback(self._handle_boundary_emergency)
        
        # Start service coordination tasks
        self._service_task = asyncio.create_task(self._safety_coordination_loop())
        self._emergency_task = asyncio.create_task(self._emergency_coordination_loop())
        
        # Subscribe to position updates
        await self.mqtt_client.subscribe("lawnberry/sensors/gps", self._handle_position_update)
        await self.mqtt_client.subscribe("lawnberry/system/state", self._handle_system_state_change)
        
        logger.info("Safety service started successfully")
        
    async def stop(self):
        """Stop the safety service"""
        logger.info("Stopping safety monitoring service")
        self._running = False
        
        # Cancel tasks
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
        
        # Stop all components
        await self.safety_monitor.stop()
        await self.emergency_controller.stop()
        await self.hazard_detector.stop()
        await self.boundary_monitor.stop()
        
        logger.info("Safety service stopped")
    
    async def _subscribe_to_commands(self):
        """Subscribe to safety-related commands"""
        await self.mqtt_client.subscribe("safety/emergency_stop", self._handle_emergency_stop_command)
        await self.mqtt_client.subscribe("lawnberry/commands/emergency", self._handle_emergency_command)
        await self.mqtt_client.subscribe("lawnberry/safety/test", self._handle_safety_test)
    
    async def _handle_emergency_stop_command(self, topic: str, message: MessageProtocol):
        """Handle external emergency stop command"""
        try:
            command_data = message.payload
            reason = command_data.get('reason', 'External emergency stop command')
            triggered_by = command_data.get('triggered_by', 'unknown')
            
            logger.critical(f"Emergency stop commanded by {triggered_by}: {reason}")
            
            # Trigger immediate emergency response
            await self.trigger_emergency_stop(reason=reason, triggered_by=triggered_by)
            
        except Exception as e:
            logger.error(f"Error handling emergency stop command: {e}")
    
    async def _handle_emergency_command(self, topic: str, message: MessageProtocol):
        """Handle emergency commands"""
        try:
            command_data = message.payload
            command = command_data.get('command')
            
            if command == 'emergency_stop':
                await self._handle_emergency_stop_command(topic, message)
            elif command == 'safety_override':
                await self._handle_safety_override(command_data)
            elif command == 'reset_safety':
                await self._handle_safety_reset(command_data)
            
        except Exception as e:
            logger.error(f"Error handling emergency command: {e}")
    
    async def _handle_position_update(self, topic: str, message: MessageProtocol):
        """Handle GPS position updates for boundary monitoring"""
        try:
            gps_data = message.payload
            self._current_position = GPSReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
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
    
    async def _handle_system_state_change(self, topic: str, message: MessageProtocol):
        """Handle system state changes"""
        try:
            state_data = message.payload
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
                
                # Publish comprehensive safety status
                await self._publish_comprehensive_safety_status(safety_status)
                
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
            # Get status from all safety components
            safety_monitor_status = self.safety_monitor.get_current_safety_status()
            hazard_detector_status = await self.hazard_detector.get_current_status()
            boundary_status = await self.boundary_monitor.get_current_status() if self.config.enable_boundary_enforcement else None
            emergency_controller_status = self.emergency_controller.get_current_status()
            
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
                    'boundary_monitor': boundary_status,
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
            
            for component_name, component_status in comprehensive_status['components'].items():
                if component_status and not component_status.get('is_safe', True):
                    all_components_safe = False
                    
                # Collect alerts from all components
                if component_status and 'active_alerts' in component_status:
                    comprehensive_status['active_alerts'].extend(component_status['active_alerts'])
            
            comprehensive_status['overall_safe'] = all_components_safe
            
            # Determine overall safety level
            if comprehensive_status['active_alerts']:
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
            logger.error(f"Error collecting comprehensive safety status: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_safe': False,
                'safety_level': 'CRITICAL',
                'error': str(e)
            }
    
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
