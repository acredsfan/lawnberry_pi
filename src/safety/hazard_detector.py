"""
Hazard Detector - Comprehensive hazard detection including vision-based safety
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass
import numpy as np

from ..communication import MQTTClient, MessageProtocol, SensorData
from ..sensor_fusion.data_structures import HazardLevel, HazardAlert

logger = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    """Detected object from vision system"""
    object_id: str
    object_type: str  # person, pet, obstacle, vehicle, etc.
    confidence: float
    distance: float
    position: Tuple[float, float]  # x, y relative to robot
    velocity: Tuple[float, float]  # x, y velocity if tracked
    timestamp: datetime
    threat_level: HazardLevel


class HazardDetector:
    """
    Comprehensive hazard detection system that combines multiple sensor inputs
    for enhanced safety including vision-based person and pet detection
    """
    
    def __init__(self, mqtt_client: MQTTClient, config):
        self.mqtt_client = mqtt_client
        self.config = config
        
        # Detection state
        self._detected_objects: Dict[str, DetectedObject] = {}
        self._vision_enabled = config.enable_vision_safety
        self._weather_hazards_enabled = config.enable_weather_safety
        
        # Safety zones and thresholds
        self._person_safety_radius = config.person_safety_radius_m
        self._pet_safety_radius = config.pet_safety_radius_m
        self._emergency_stop_distance = config.emergency_stop_distance_m
        
        # Object tracking
        self._object_tracking_timeout = 3.0  # seconds
        self._velocity_history: Dict[str, List[Tuple[datetime, Tuple[float, float]]]] = {}
        
        # Hazard classification
        self._hazard_patterns = self._initialize_hazard_patterns()
        
        # Performance tracking
        self._detection_count = 0
        self._false_positive_count = 0
        self._detection_accuracy = 0.0
        
        # Emergency callbacks
        self._emergency_callbacks: List[Callable] = []
        
        # Tasks
        self._detection_task: Optional[asyncio.Task] = None
        self._tracking_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the hazard detection system"""
        logger.info("Starting hazard detection system")
        self._running = True
        
        # Subscribe to sensor data
        await self._subscribe_to_sensors()
        
        # Start detection and tracking tasks
        self._detection_task = asyncio.create_task(self._hazard_detection_loop())
        self._tracking_task = asyncio.create_task(self._object_tracking_loop())
        
        logger.info("Hazard detection system started")
    
    async def stop(self):
        """Stop the hazard detection system"""
        logger.info("Stopping hazard detection system")
        self._running = False
        
        if self._detection_task:
            self._detection_task.cancel()
            try:
                await self._detection_task
            except asyncio.CancelledError:
                pass
        
        if self._tracking_task:
            self._tracking_task.cancel()
            try:
                await self._tracking_task
            except asyncio.CancelledError:
                pass
    
    def _initialize_hazard_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Initialize hazard detection patterns"""
        return {
            'person': {
                'safety_radius': self._person_safety_radius,
                'threat_level': HazardLevel.CRITICAL,
                'response_action': 'immediate_stop',
                'alert_message': 'Person detected in safety zone'
            },
            'pet': {
                'safety_radius': self._pet_safety_radius,
                'threat_level': HazardLevel.HIGH,
                'response_action': 'stop_and_wait',
                'alert_message': 'Pet detected in safety zone'
            },
            'child': {
                'safety_radius': self._person_safety_radius * 1.5,  # Larger safety zone for children
                'threat_level': HazardLevel.CRITICAL,
                'response_action': 'immediate_stop',
                'alert_message': 'Child detected - immediate stop required'
            },
            'vehicle': {
                'safety_radius': 5.0,
                'threat_level': HazardLevel.HIGH,
                'response_action': 'stop_and_assess',
                'alert_message': 'Vehicle detected in area'
            },
            'large_obstacle': {
                'safety_radius': 0.5,
                'threat_level': HazardLevel.MEDIUM,
                'response_action': 'navigate_around',
                'alert_message': 'Large obstacle detected'
            },
            'water_hazard': {
                'safety_radius': 1.0,
                'threat_level': HazardLevel.HIGH,
                'response_action': 'avoid_area',
                'alert_message': 'Water hazard detected'
            }
        }
    
    async def _subscribe_to_sensors(self):
        """Subscribe to relevant sensor data"""
        subscriptions = [
            ("lawnberry/vision/detections", self._handle_vision_detections),
            ("lawnberry/sensors/weather", self._handle_weather_data),
            ("lawnberry/sensors/environmental", self._handle_environmental_data),
            ("lawnberry/vision/alerts", self._handle_vision_alerts)
        ]
        
        for topic, handler in subscriptions:
            await self.mqtt_client.subscribe(topic, handler)
    
    async def _handle_vision_detections(self, topic: str, message: MessageProtocol):
        """Handle object detections from vision system"""
        try:
            detection_data = message.payload
            detections = detection_data.get('detections', [])
            
            for detection in detections:
                await self._process_object_detection(detection)
                
        except Exception as e:
            logger.error(f"Error handling vision detections: {e}")
    
    async def _process_object_detection(self, detection: Dict[str, Any]):
        """Process individual object detection"""
        try:
            object_id = detection.get('object_id', f"obj_{datetime.now().timestamp()}")
            object_type = detection.get('class', 'unknown')
            confidence = detection.get('confidence', 0.0)
            
            # Calculate distance and position
            bbox = detection.get('bbox', [0, 0, 0, 0])
            distance = self._estimate_distance_from_bbox(bbox, object_type)
            position = self._calculate_object_position(bbox, distance)
            
            # Determine threat level
            threat_level = self._assess_threat_level(object_type, distance, confidence)
            
            # Create detected object
            detected_obj = DetectedObject(
                object_id=object_id,
                object_type=object_type,
                confidence=confidence,
                distance=distance,
                position=position,
                velocity=(0.0, 0.0),  # Will be calculated by tracking
                timestamp=datetime.now(),
                threat_level=threat_level
            )
            
            # Update object tracking
            await self._update_object_tracking(detected_obj)
            
            # Check for immediate hazards
            if threat_level in [HazardLevel.CRITICAL, HazardLevel.HIGH]:
                await self._handle_immediate_hazard(detected_obj)
            
            self._detection_count += 1
            
        except Exception as e:
            logger.error(f"Error processing object detection: {e}")
    
    def _estimate_distance_from_bbox(self, bbox: List[float], object_type: str) -> float:
        """Estimate distance based on bounding box size and object type"""
        try:
            # bbox format: [x, y, width, height] normalized to image size
            width, height = bbox[2], bbox[3]
            
            # Rough distance estimation based on known object sizes
            typical_sizes = {
                'person': 1.7,      # Average person height in meters
                'child': 1.2,       # Average child height
                'pet': 0.5,         # Average pet size
                'dog': 0.6,
                'cat': 0.3,
                'car': 4.5,         # Average car length
                'bicycle': 1.8
            }
            
            typical_size = typical_sizes.get(object_type, 1.0)
            
            # Simple distance estimation (this would be improved with stereo vision or depth sensors)
            # Assuming camera FOV and image resolution
            image_height = 1080  # pixels
            camera_fov_vertical = 62.2  # degrees for Pi camera
            
            # Calculate angular size and estimate distance
            angular_size = (height * camera_fov_vertical) / image_height
            if angular_size > 0:
                distance = typical_size / (2 * np.tan(np.radians(angular_size / 2)))
                return max(0.1, min(50.0, distance))  # Clamp to reasonable range
            
            return 10.0  # Default distance if calculation fails
            
        except Exception as e:
            logger.error(f"Error estimating distance: {e}")
            return 10.0
    
    def _calculate_object_position(self, bbox: List[float], distance: float) -> Tuple[float, float]:
        """Calculate object position relative to robot"""
        try:
            # bbox format: [x, y, width, height] normalized
            center_x = bbox[0] + bbox[2] / 2
            center_y = bbox[1] + bbox[3] / 2
            
            # Convert to robot-relative coordinates
            # Assuming camera is front-facing at robot center
            camera_fov_horizontal = 82.6  # degrees for Pi camera
            
            # Calculate angle from robot forward direction
            angle_rad = np.radians((center_x - 0.5) * camera_fov_horizontal)
            
            # Calculate x, y position relative to robot
            x = distance * np.sin(angle_rad)  # Lateral offset
            y = distance * np.cos(angle_rad)  # Forward distance
            
            return (x, y)
            
        except Exception as e:
            logger.error(f"Error calculating object position: {e}")
            return (0.0, distance)
    
    def _assess_threat_level(self, object_type: str, distance: float, confidence: float) -> HazardLevel:
        """Assess threat level based on object type, distance, and confidence"""
        try:
            # Get hazard pattern for object type
            pattern = self._hazard_patterns.get(object_type, {})
            base_threat_level = pattern.get('threat_level', HazardLevel.LOW)
            safety_radius = pattern.get('safety_radius', 1.0)
            
            # Adjust threat level based on distance
            if distance <= self._emergency_stop_distance:
                return HazardLevel.CRITICAL
            elif distance <= safety_radius:
                return max(base_threat_level, HazardLevel.HIGH)
            elif distance <= safety_radius * 2:
                return HazardLevel.MEDIUM
            else:
                return HazardLevel.LOW
            
        except Exception as e:
            logger.error(f"Error assessing threat level: {e}")
            return HazardLevel.MEDIUM
    
    async def _update_object_tracking(self, detected_obj: DetectedObject):
        """Update object tracking and velocity estimation"""
        try:
            object_id = detected_obj.object_id
            current_time = detected_obj.timestamp
            current_pos = detected_obj.position
            
            # Store current detection
            self._detected_objects[object_id] = detected_obj
            
            # Update velocity history
            if object_id not in self._velocity_history:
                self._velocity_history[object_id] = []
            
            self._velocity_history[object_id].append((current_time, current_pos))
            
            # Keep only recent history (last 3 seconds)
            cutoff_time = current_time - timedelta(seconds=3)
            self._velocity_history[object_id] = [
                (t, pos) for t, pos in self._velocity_history[object_id]
                if t > cutoff_time
            ]
            
            # Calculate velocity if we have enough history
            if len(self._velocity_history[object_id]) >= 2:
                velocity = self._calculate_object_velocity(object_id)
                detected_obj.velocity = velocity
                
                # Update threat level based on velocity (approaching objects are more dangerous)
                if self._is_object_approaching(velocity, current_pos):
                    detected_obj.threat_level = min(HazardLevel.CRITICAL, 
                                                  HazardLevel(detected_obj.threat_level.value + 1))
            
        except Exception as e:
            logger.error(f"Error updating object tracking: {e}")
    
    def _calculate_object_velocity(self, object_id: str) -> Tuple[float, float]:
        """Calculate object velocity from position history"""
        try:
            history = self._velocity_history[object_id]
            if len(history) < 2:
                return (0.0, 0.0)
            
            # Use last two positions for velocity calculation
            (t1, pos1), (t2, pos2) = history[-2], history[-1]
            dt = (t2 - t1).total_seconds()
            
            if dt > 0:
                vx = (pos2[0] - pos1[0]) / dt
                vy = (pos2[1] - pos1[1]) / dt
                return (vx, vy)
            
            return (0.0, 0.0)
            
        except Exception as e:
            logger.error(f"Error calculating object velocity: {e}")
            return (0.0, 0.0)
    
    def _is_object_approaching(self, velocity: Tuple[float, float], position: Tuple[float, float]) -> bool:
        """Check if object is approaching the robot"""
        try:
            vx, vy = velocity
            x, y = position
            
            # Calculate if velocity vector points toward robot (origin)
            # Dot product of velocity and position vectors
            dot_product = vx * x + vy * y
            
            # If dot product is negative, object is moving toward robot
            return dot_product < -0.1  # Small threshold to avoid noise
            
        except Exception as e:
            logger.error(f"Error checking if object approaching: {e}")
            return False
    
    async def _handle_immediate_hazard(self, detected_obj: DetectedObject):
        """Handle immediate hazard detection"""
        try:
            object_type = detected_obj.object_type
            distance = detected_obj.distance
            threat_level = detected_obj.threat_level
            
            # Create hazard alert
            alert = {
                'alert_id': f"hazard_{detected_obj.object_id}",
                'hazard_level': threat_level.value,
                'hazard_type': f"{object_type}_detection",
                'timestamp': detected_obj.timestamp.isoformat(),
                'description': f"{object_type.title()} detected at {distance:.1f}m",
                'location': detected_obj.position,
                'sensor_data': {
                    'object_type': object_type,
                    'distance': distance,
                    'confidence': detected_obj.confidence,
                    'velocity': detected_obj.velocity,
                    'threat_level': threat_level.value
                },
                'immediate_response_required': threat_level == HazardLevel.CRITICAL
            }
            
            # Get recommended action from hazard pattern
            pattern = self._hazard_patterns.get(object_type, {})
            alert['recommended_action'] = pattern.get('response_action', 'STOP')
            
            # Publish hazard alert
            await self._publish_hazard_alert(alert)
            
            # Trigger emergency callbacks if critical
            if threat_level == HazardLevel.CRITICAL:
                for callback in self._emergency_callbacks:
                    try:
                        await callback([alert])
                    except Exception as e:
                        logger.error(f"Error in emergency callback: {e}")
            
        except Exception as e:
            logger.error(f"Error handling immediate hazard: {e}")
    
    async def _hazard_detection_loop(self):
        """Main hazard detection and analysis loop"""
        while self._running:
            try:
                # Clean up old detections
                await self._cleanup_old_detections()
                
                # Analyze current hazard situation
                hazard_analysis = await self._analyze_hazard_situation()
                
                # Update detection accuracy metrics
                self._update_detection_metrics()
                
                await asyncio.sleep(0.1)  # 10Hz update rate
                
            except Exception as e:
                logger.error(f"Error in hazard detection loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _object_tracking_loop(self):
        """Object tracking and prediction loop"""
        while self._running:
            try:
                # Update object predictions
                await self._update_object_predictions()
                
                # Check for collision predictions
                await self._check_collision_predictions()
                
                await asyncio.sleep(0.05)  # 20Hz tracking rate
                
            except Exception as e:
                logger.error(f"Error in object tracking loop: {e}")
                await asyncio.sleep(0.05)
    
    async def check_critical_hazards(self) -> List[Dict[str, Any]]:
        """Check for critical hazards requiring immediate response"""
        critical_hazards = []
        
        try:
            current_time = datetime.now()
            
            for obj_id, detected_obj in self._detected_objects.items():
                # Check if detection is recent (within last 2 seconds)
                if (current_time - detected_obj.timestamp).total_seconds() > 2.0:
                    continue
                
                # Check for critical threat levels
                if detected_obj.threat_level == HazardLevel.CRITICAL:
                    critical_hazards.append({
                        'source': 'hazard_detector',
                        'alert': {
                            'hazard_type': f"critical_{detected_obj.object_type}",
                            'hazard_level': 'CRITICAL',
                            'description': f"Critical hazard: {detected_obj.object_type} at {detected_obj.distance:.1f}m",
                            'immediate_response_required': True,
                            'object_data': {
                                'object_type': detected_obj.object_type,
                                'distance': detected_obj.distance,
                                'position': detected_obj.position,
                                'velocity': detected_obj.velocity,
                                'confidence': detected_obj.confidence
                            }
                        }
                    })
            
        except Exception as e:
            logger.error(f"Error checking critical hazards: {e}")
            critical_hazards.append({
                'source': 'hazard_detector',
                'alert': {
                    'hazard_type': 'system_error',
                    'hazard_level': 'CRITICAL',
                    'description': f"Hazard detector error: {e}",
                    'immediate_response_required': True
                }
            })
        
        return critical_hazards
    
    async def get_current_status(self) -> Dict[str, Any]:
        """Get current hazard detector status"""
        current_time = datetime.now()
        
        # Get recent detections
        recent_detections = [
            {
                'object_id': obj.object_id,
                'object_type': obj.object_type,
                'distance': obj.distance,
                'threat_level': obj.threat_level.value,
                'confidence': obj.confidence,
                'age_seconds': (current_time - obj.timestamp).total_seconds()
            }
            for obj in self._detected_objects.values()
            if (current_time - obj.timestamp).total_seconds() < 10.0
        ]
        
        # Count active hazards by level
        hazard_counts = {level.value: 0 for level in HazardLevel}
        for obj in self._detected_objects.values():
            if (current_time - obj.timestamp).total_seconds() < 5.0:
                hazard_counts[obj.threat_level.value] += 1
        
        return {
            'is_safe': hazard_counts['CRITICAL'] == 0 and hazard_counts['HIGH'] == 0,
            'total_detections': len(recent_detections),
            'hazard_counts': hazard_counts,
            'recent_detections': recent_detections,
            'vision_enabled': self._vision_enabled,
            'detection_accuracy': self._detection_accuracy,
            'false_positive_rate': self._false_positive_count / max(1, self._detection_count)
        }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get hazard detector performance metrics"""
        return {
            'total_detections': self._detection_count,
            'false_positives': self._false_positive_count,
            'detection_accuracy': self._detection_accuracy,
            'active_objects': len(self._detected_objects),
            'vision_enabled': self._vision_enabled,
            'weather_hazards_enabled': self._weather_hazards_enabled
        }
    
    def register_emergency_callback(self, callback: Callable):
        """Register callback for emergency situations"""
        self._emergency_callbacks.append(callback)
    
    # Additional methods for weather hazards, cleanup, etc. would continue here...
    async def _handle_weather_data(self, topic: str, message: MessageProtocol):
        """Handle weather-related hazard detection"""
        # Implementation for weather hazard detection
        pass
    
    async def _handle_environmental_data(self, topic: str, message: MessageProtocol):
        """Handle environmental hazard detection"""
        # Implementation for environmental hazard detection
        pass
    
    async def _cleanup_old_detections(self):
        """Clean up old object detections"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(seconds=self._object_tracking_timeout)
        
        # Remove old detections
        expired_objects = [
            obj_id for obj_id, obj in self._detected_objects.items()
            if obj.timestamp < cutoff_time
        ]
        
        for obj_id in expired_objects:
            del self._detected_objects[obj_id]
            if obj_id in self._velocity_history:
                del self._velocity_history[obj_id]
