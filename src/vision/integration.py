"""Integration utilities for computer vision system with other subsystems"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

from ..sensor_fusion.fusion_engine import SensorFusionEngine
from ..sensor_fusion.data_structures import SensorReading
from ..communication.client import MQTTClient
from .data_structures import VisionFrame, DetectedObject, ObjectType, SafetyLevel
from .vision_manager import VisionManager


class VisionIntegrationManager:
    """Manages integration between vision system and other subsystems"""
    
    def __init__(self, vision_manager: VisionManager, 
                 sensor_fusion_engine: Optional[SensorFusionEngine] = None,
                 mqtt_client: Optional[MQTTClient] = None):
        self.logger = logging.getLogger(__name__)
        self.vision_manager = vision_manager
        self.sensor_fusion_engine = sensor_fusion_engine
        self.mqtt_client = mqtt_client
        
        # Integration state
        self._integration_active = False
        self._safety_callbacks = []
        self._navigation_callbacks = []
        
    async def initialize_integration(self) -> bool:
        """Initialize all integrations"""
        try:
            self.logger.info("Initializing vision system integrations...")
            
            # Setup sensor fusion integration
            if self.sensor_fusion_engine:
                await self._setup_sensor_fusion_integration()
            
            # Setup MQTT integrations
            if self.mqtt_client:
                await self._setup_mqtt_integrations()
            
            # Register vision safety callbacks
            self.vision_manager.register_safety_callback(self._handle_safety_detection)
            
            self._integration_active = True
            self.logger.info("Vision system integrations initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing vision integrations: {e}")
            return False
    
    async def _setup_sensor_fusion_integration(self):
        """Setup integration with sensor fusion engine"""
        try:
            # Subscribe to ToF sensor data for distance validation
            await self.sensor_fusion_engine.subscribe_to_sensor_data(
                'tof_left', self._validate_tof_distance
            )
            await self.sensor_fusion_engine.subscribe_to_sensor_data(
                'tof_right', self._validate_tof_distance
            )
            
            self.logger.info("Sensor fusion integration setup complete")
            
        except Exception as e:
            self.logger.error(f"Error setting up sensor fusion integration: {e}")
    
    async def _setup_mqtt_integrations(self):
        """Setup MQTT-based integrations"""
        try:
            def wrap(func):
                async def _w(topic, message):
                    payload = message.payload if hasattr(message, 'payload') else message
                    await func(topic, payload)
                return _w

            # Subscribe to navigation commands
            await self.mqtt_client.subscribe("lawnberry/navigation/obstacle_request")
            self.mqtt_client.add_message_handler(
                "lawnberry/navigation/obstacle_request", wrap(self._handle_obstacle_request)
            )
            
            # Subscribe to safety system commands
            await self.mqtt_client.subscribe("lawnberry/safety/vision_request")
            self.mqtt_client.add_message_handler(
                "lawnberry/safety/vision_request", wrap(self._handle_safety_request)
            )
            
            # Subscribe to power management requests
            await self.mqtt_client.subscribe("lawnberry/power/vision_mode")
            self.mqtt_client.add_message_handler(
                "lawnberry/power/vision_mode", wrap(self._handle_power_mode_change)
            )
            
            self.logger.info("MQTT integrations setup complete")
            
        except Exception as e:
            self.logger.error(f"Error setting up MQTT integrations: {e}")
    
    async def _validate_tof_distance(self, sensor_data: SensorReading):
        """Validate vision-detected distances with ToF sensor data"""
        try:
            if not hasattr(sensor_data, 'distance_mm'):
                return
            
            tof_distance_m = sensor_data.distance_mm / 1000.0
            
            # Get latest vision frame
            latest_stats = await self.vision_manager.get_system_statistics()
            
            # Compare with vision detections (simplified validation)
            # In practice, this would correlate ToF data with specific detected objects
            if tof_distance_m < 1.0:  # Object within 1 meter
                self.logger.debug(f"ToF sensor confirms close object: {tof_distance_m:.2f}m")
                
                # Publish enhanced obstacle data
                if self.mqtt_client:
                    obstacle_data = {
                        'timestamp': datetime.now().isoformat(),
                        'type': 'confirmed_obstacle',
                        'distance_vision': None,  # Would extract from latest detection
                        'distance_tof': tof_distance_m,
                        'sensor_name': sensor_data.metadata.get('sensor_name', 'unknown'),
                        'confidence': 'high'
                    }
                    
                    await self.mqtt_client.publish(
                        "lawnberry/sensor_fusion/obstacle_confirmation",
                        obstacle_data,
                        qos=1
                    )
            
        except Exception as e:
            self.logger.error(f"Error validating ToF distance: {e}")
    
    async def _handle_safety_detection(self, critical_objects: List[DetectedObject]):
        """Handle safety-critical detections from vision system"""
        try:
            self.logger.warning(f"Vision safety handler: {len(critical_objects)} critical objects")
            
            # Categorize objects by type
            people = [obj for obj in critical_objects if obj.object_type == ObjectType.PERSON]
            pets = [obj for obj in critical_objects if obj.object_type == ObjectType.PET]
            hazards = [obj for obj in critical_objects if obj.object_type in [
                ObjectType.HOSE, ObjectType.CABLE, ObjectType.HOLE
            ]]
            
            # Send immediate safety alerts
            if people:
                await self._send_safety_alert("PERSON_DETECTED", people)
            
            if pets:
                await self._send_safety_alert("PET_DETECTED", pets)
            
            if hazards:
                await self._send_safety_alert("HAZARD_DETECTED", hazards)
            
            # Call registered safety callbacks
            for callback in self._safety_callbacks:
                try:
                    await callback(critical_objects)
                except Exception as e:
                    self.logger.error(f"Error in safety callback: {e}")
            
        except Exception as e:
            self.logger.error(f"Error handling safety detection: {e}")
    
    async def _send_safety_alert(self, alert_type: str, objects: List[DetectedObject]):
        """Send safety alert via MQTT"""
        try:
            if not self.mqtt_client:
                return
            
            alert_data = {
                'timestamp': datetime.now().isoformat(),
                'alert_type': alert_type,
                'object_count': len(objects),
                'objects': [],
                'recommended_action': self._get_recommended_action(alert_type),
                'priority': 'CRITICAL'
            }
            
            for obj in objects:
                obj_data = {
                    'type': obj.object_type.value,
                    'confidence': obj.confidence,
                    'distance_estimate': obj.distance_estimate,
                    'safety_level': obj.safety_level.value,
                    'bbox_center': obj.bounding_box.center
                }
                alert_data['objects'].append(obj_data)
            
            # Send to safety system
            await self.mqtt_client.publish(
                "lawnberry/safety/emergency_alert",
                alert_data,
                qos=2  # Ensure delivery
            )
            
            # Send to navigation system for immediate response
            await self.mqtt_client.publish(
                "lawnberry/navigation/emergency_stop",
                {
                    'reason': alert_type,
                    'timestamp': datetime.now().isoformat(),
                    'object_count': len(objects)
                },
                qos=2
            )
            
        except Exception as e:
            self.logger.error(f"Error sending safety alert: {e}")
    
    def _get_recommended_action(self, alert_type: str) -> str:
        """Get recommended action for alert type"""
        actions = {
            'PERSON_DETECTED': 'EMERGENCY_STOP_AND_WAIT',
            'PET_DETECTED': 'EMERGENCY_STOP_AND_WAIT',
            'HAZARD_DETECTED': 'EMERGENCY_STOP_AND_NAVIGATE_AROUND'
        }
        return actions.get(alert_type, 'EMERGENCY_STOP')
    
    async def _handle_obstacle_request(self, topic: str, payload: Dict[str, Any]):
        """Handle obstacle detection requests from navigation system"""
        try:
            request_type = payload.get('request_type')
            
            if request_type == 'current_obstacles':
                # Get current vision detections
                stats = await self.vision_manager.get_system_statistics()
                
                # This would be enhanced to get actual current detections
                response = {
                    'timestamp': datetime.now().isoformat(),
                    'request_id': payload.get('request_id'),
                    'obstacles': [],  # Would populate with current detections
                    'scan_complete': True
                }
                
                await self.mqtt_client.publish(
                    "lawnberry/navigation/obstacle_response",
                    response,
                    qos=1
                )
            
            elif request_type == 'scan_area':
                # Perform focused scanning of specific area
                area = payload.get('area', {})
                self.logger.info(f"Scanning area: {area}")
                
                # This would trigger focused analysis of the specified area
                # For now, just acknowledge
                response = {
                    'timestamp': datetime.now().isoformat(),
                    'request_id': payload.get('request_id'),
                    'scan_result': 'completed',
                    'obstacles_found': 0
                }
                
                await self.mqtt_client.publish(
                    "lawnberry/navigation/scan_response",
                    response,
                    qos=1
                )
            
        except Exception as e:
            self.logger.error(f"Error handling obstacle request: {e}")
    
    async def _handle_safety_request(self, topic: str, payload: Dict[str, Any]):
        """Handle safety system requests"""
        try:
            request_type = payload.get('request_type')
            
            if request_type == 'perform_safety_scan':
                # Perform comprehensive safety scan
                self.logger.info("Performing safety scan")
                
                # This would trigger a focused safety scan
                # For now, get current system status
                stats = await self.vision_manager.get_system_statistics()
                
                response = {
                    'timestamp': datetime.now().isoformat(),
                    'request_id': payload.get('request_id'),
                    'scan_result': 'safe',  # Would be determined by actual scan
                    'critical_objects_detected': 0,
                    'processing_performance': {
                        'current_fps': stats['system'].get('current_fps', 0),
                        'average_latency_ms': stats['system'].get('average_latency_ms', 0)
                    }
                }
                
                await self.mqtt_client.publish(
                    "lawnberry/safety/scan_response",
                    response,
                    qos=1
                )
            
        except Exception as e:
            self.logger.error(f"Error handling safety request: {e}")
    
    async def _handle_power_mode_change(self, topic: str, payload: Dict[str, Any]):
        """Handle power management mode changes"""
        try:
            power_mode = payload.get('mode')
            
            if power_mode == 'eco':
                # Reduce vision processing for power saving
                self.logger.info("Switching to eco vision mode")
                
                # Update vision config for power saving
                eco_config = {
                    'confidence_threshold': 0.7,  # Higher threshold = less processing
                    'max_processing_time_ms': 150.0,  # Allow more time but process less frequently
                    'enable_continuous_learning': False  # Disable training in eco mode
                }
                
                await self.vision_manager._update_config(eco_config)
                
            elif power_mode == 'performance':
                # Full performance vision processing
                self.logger.info("Switching to performance vision mode")
                
                performance_config = {
                    'confidence_threshold': 0.5,
                    'max_processing_time_ms': 100.0,
                    'enable_continuous_learning': True
                }
                
                await self.vision_manager._update_config(performance_config)
            
            elif power_mode == 'low_power':
                # Minimal vision processing
                self.logger.info("Switching to low power vision mode")
                
                # Could pause vision processing entirely or reduce to safety-only
                if self.vision_manager._processing_active:
                    await self.vision_manager.stop_processing()
            
        except Exception as e:
            self.logger.error(f"Error handling power mode change: {e}")
    
    def register_safety_callback(self, callback: Callable):
        """Register additional safety callback"""
        self._safety_callbacks.append(callback)
    
    def register_navigation_callback(self, callback: Callable):
        """Register navigation integration callback"""
        self._navigation_callbacks.append(callback)
    
    async def get_integration_status(self) -> Dict[str, Any]:
        """Get integration system status"""
        try:
            return {
                'integration_active': self._integration_active,
                'sensor_fusion_connected': self.sensor_fusion_engine is not None,
                'mqtt_connected': self.mqtt_client is not None,
                'safety_callbacks_registered': len(self._safety_callbacks),
                'navigation_callbacks_registered': len(self._navigation_callbacks),
                'vision_system_status': await self.vision_manager.get_system_statistics()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting integration status: {e}")
            return {'error': str(e)}
    
    async def shutdown_integration(self):
        """Shutdown all integrations"""
        try:
            self.logger.info("Shutting down vision system integrations...")
            
            self._integration_active = False
            
            # Clean up callbacks
            self._safety_callbacks.clear()
            self._navigation_callbacks.clear()
            
            self.logger.info("Vision system integrations shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during integration shutdown: {e}")


# Utility functions for integration
def create_obstacle_message(detected_objects: List[DetectedObject]) -> Dict[str, Any]:
    """Create standardized obstacle message for navigation system"""
    obstacles = []
    
    for obj in detected_objects:
        obstacle = {
            'type': obj.object_type.value,
            'confidence': obj.confidence,
            'safety_level': obj.safety_level.value,
            'position': {
                'x': obj.bounding_box.center[0],
                'y': obj.bounding_box.center[1]
            },
            'size': {
                'width': obj.bounding_box.width,
                'height': obj.bounding_box.height
            },
            'distance_estimate': obj.distance_estimate
        }
        obstacles.append(obstacle)
    
    return {
        'timestamp': datetime.now().isoformat(),
        'obstacle_count': len(obstacles),
        'obstacles': obstacles,
        'source': 'computer_vision'
    }


def filter_objects_by_safety_level(objects: List[DetectedObject], 
                                 min_level: SafetyLevel) -> List[DetectedObject]:
    """Filter objects by minimum safety level"""
    level_priority = {
        SafetyLevel.LOW: 0,
        SafetyLevel.MEDIUM: 1,
        SafetyLevel.HIGH: 2,
        SafetyLevel.CRITICAL: 3
    }
    
    min_priority = level_priority[min_level]
    return [obj for obj in objects 
            if level_priority[obj.safety_level] >= min_priority]


def estimate_collision_risk(detected_object: DetectedObject, 
                          current_speed: float = 1.0) -> float:
    """Estimate collision risk based on object properties and current speed"""
    try:
        if not detected_object.distance_estimate:
            return 1.0  # High risk if distance unknown
        
        # Simple risk calculation based on distance and speed
        time_to_collision = detected_object.distance_estimate / current_speed
        
        # Risk factors
        distance_risk = max(0, 1 - (detected_object.distance_estimate / 5.0))  # Higher risk closer than 5m
        confidence_risk = 1 - detected_object.confidence  # Higher risk if low confidence
        safety_risk = {
            SafetyLevel.LOW: 0.1,
            SafetyLevel.MEDIUM: 0.3,
            SafetyLevel.HIGH: 0.7,
            SafetyLevel.CRITICAL: 1.0
        }[detected_object.safety_level]
        
        # Combine risk factors
        total_risk = min(1.0, distance_risk + confidence_risk + safety_risk)
        
        return total_risk
        
    except Exception:
        return 1.0  # Return high risk on any error
