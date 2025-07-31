"""
Advanced Sensor Fusion Safety System
Implements multi-sensor fusion for enhanced obstacle detection and safety monitoring
"""

import asyncio
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import statistics

from ..hardware.data_structures import IMUReading, ToFReading, EnvironmentalReading, CameraFrame
from ..communication import MQTTClient, MessageProtocol, SensorData
from .data_structures import SafetyStatus, HazardAlert, HazardLevel, ObstacleInfo

logger = logging.getLogger(__name__)


class SensorType(Enum):
    """Types of sensors in the fusion system"""
    TOF_LEFT = "tof_left"
    TOF_RIGHT = "tof_right"
    CAMERA_VISION = "camera_vision"
    IMU = "imu"
    ENVIRONMENTAL = "environmental"


class SensorReliability(Enum):
    """Sensor reliability levels"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    FAILED = "failed"


@dataclass
class SensorReading:
    """Unified sensor reading with confidence and reliability"""
    sensor_type: SensorType
    timestamp: datetime
    data: Any
    confidence: float  # 0.0 to 1.0
    reliability: SensorReliability
    environmental_factors: Dict[str, float] = field(default_factory=dict)


@dataclass
class FusedObstacleDetection:
    """Result of multi-sensor obstacle detection"""
    obstacle_id: str
    position: Tuple[float, float, float]  # x, y, z relative to mower
    size: Tuple[float, float, float]  # width, height, depth
    confidence: float
    threat_level: HazardLevel
    contributing_sensors: List[SensorType]
    sensor_agreements: Dict[SensorType, float]
    predicted_trajectory: Optional[List[Tuple[float, float, float]]] = None
    classification: str = "unknown"


@dataclass
class EnvironmentalConditions:
    """Current environmental conditions affecting sensor performance"""
    temperature: float
    humidity: float
    light_level: float
    weather_condition: str
    wind_speed: float
    precipitation: bool
    visibility_factor: float  # 0.0 to 1.0


class SensorFusionSafetySystem:
    """Advanced multi-sensor fusion system for enhanced safety"""
    
    def __init__(self, mqtt_client: MQTTClient, config: Dict[str, Any]):
        self.mqtt_client = mqtt_client
        self.config = config
        
        # Sensor management
        self.sensor_readings: Dict[SensorType, List[SensorReading]] = {
            sensor_type: [] for sensor_type in SensorType
        }
        self.sensor_reliability: Dict[SensorType, SensorReliability] = {
            sensor_type: SensorReliability.GOOD for sensor_type in SensorType
        }
        self.sensor_weights: Dict[SensorType, float] = self._initialize_sensor_weights()
        
        # Fusion parameters
        self.reading_history_size = 50  # Keep last 50 readings per sensor
        self.fusion_window_ms = 100  # Time window for sensor fusion
        self.confidence_threshold = 0.7  # Minimum confidence for obstacle detection
        self.agreement_threshold = 0.6  # Minimum sensor agreement
        
        # Environmental adaptation
        self.environmental_conditions: Optional[EnvironmentalConditions] = None
        self.adaptive_weights_enabled = True
        
        # Obstacle tracking
        self.tracked_obstacles: Dict[str, FusedObstacleDetection] = {}
        self.obstacle_persistence_threshold = 3  # Detections needed to confirm obstacle
        self.obstacle_timeout_seconds = 2.0  # Remove obstacles not seen for this time
        
        # Predictive detection
        self.enable_predictive_detection = True
        self.prediction_horizon_seconds = 1.0
        self.trajectory_history_size = 10
        
        # Callbacks
        self.obstacle_callbacks: List[Callable] = []
        self.environmental_callbacks: List[Callable] = []
        
        # Performance monitoring
        self.fusion_performance_metrics = {
            'detection_accuracy': 0.0,
            'false_positive_rate': 0.0,
            'response_time_ms': 0.0,
            'sensor_fusion_rate': 0.0
        }
        
        # Tasks
        self._fusion_task: Optional[asyncio.Task] = None
        self._environmental_task: Optional[asyncio.Task] = None
        self._obstacle_tracking_task: Optional[asyncio.Task] = None
        self._running = False
    
    def _initialize_sensor_weights(self) -> Dict[SensorType, float]:
        """Initialize default sensor weights for fusion"""
        return {
            SensorType.TOF_LEFT: 0.25,
            SensorType.TOF_RIGHT: 0.25,
            SensorType.CAMERA_VISION: 0.35,
            SensorType.IMU: 0.10,
            SensorType.ENVIRONMENTAL: 0.05
        }
    
    async def start(self):
        """Start the sensor fusion safety system"""
        logger.info("Starting advanced sensor fusion safety system")
        self._running = True
        
        # Subscribe to sensor data
        await self._subscribe_to_sensors()
        
        # Start fusion tasks
        self._fusion_task = asyncio.create_task(self._sensor_fusion_loop())
        self._environmental_task = asyncio.create_task(self._environmental_monitoring_loop())
        self._obstacle_tracking_task = asyncio.create_task(self._obstacle_tracking_loop())
    
    async def stop(self):
        """Stop the sensor fusion safety system"""
        logger.info("Stopping sensor fusion safety system")
        self._running = False
        
        for task in [self._fusion_task, self._environmental_task, self._obstacle_tracking_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def _subscribe_to_sensors(self):
        """Subscribe to all sensor data streams"""
        # Subscribe to ToF sensors
        await self.mqtt_client.subscribe("sensor/tof/left", self._handle_tof_left_data)
        await self.mqtt_client.subscribe("sensor/tof/right", self._handle_tof_right_data)
        
        # Subscribe to vision data
        await self.mqtt_client.subscribe("vision/obstacles", self._handle_vision_data)
        
        # Subscribe to IMU data
        await self.mqtt_client.subscribe("sensor/imu", self._handle_imu_data)
        
        # Subscribe to environmental data
        await self.mqtt_client.subscribe("sensor/environmental", self._handle_environmental_data)
    
    async def _handle_tof_left_data(self, data: Dict[str, Any]):
        """Handle ToF left sensor data"""
        reading = SensorReading(
            sensor_type=SensorType.TOF_LEFT,
            timestamp=datetime.now(),
            data=data,
            confidence=self._calculate_tof_confidence(data),
            reliability=self.sensor_reliability[SensorType.TOF_LEFT]
        )
        await self._add_sensor_reading(reading)
    
    async def _handle_tof_right_data(self, data: Dict[str, Any]):
        """Handle ToF right sensor data"""
        reading = SensorReading(
            sensor_type=SensorType.TOF_RIGHT,
            timestamp=datetime.now(),
            data=data,
            confidence=self._calculate_tof_confidence(data),
            reliability=self.sensor_reliability[SensorType.TOF_RIGHT]
        )
        await self._add_sensor_reading(reading)
    
    async def _handle_vision_data(self, data: Dict[str, Any]):
        """Handle camera vision data"""
        reading = SensorReading(
            sensor_type=SensorType.CAMERA_VISION,
            timestamp=datetime.now(),
            data=data,
            confidence=self._calculate_vision_confidence(data),
            reliability=self.sensor_reliability[SensorType.CAMERA_VISION]
        )
        await self._add_sensor_reading(reading)
    
    async def _handle_imu_data(self, data: Dict[str, Any]):
        """Handle IMU sensor data"""
        reading = SensorReading(
            sensor_type=SensorType.IMU,
            timestamp=datetime.now(),
            data=data,
            confidence=self._calculate_imu_confidence(data),
            reliability=self.sensor_reliability[SensorType.IMU]
        )
        await self._add_sensor_reading(reading)
    
    async def _handle_environmental_data(self, data: Dict[str, Any]):
        """Handle environmental sensor data"""
        reading = SensorReading(
            sensor_type=SensorType.ENVIRONMENTAL,
            timestamp=datetime.now(),
            data=data,
            confidence=1.0,  # Environmental data is always reliable
            reliability=self.sensor_reliability[SensorType.ENVIRONMENTAL]
        )
        await self._add_sensor_reading(reading)
        
        # Update environmental conditions
        await self._update_environmental_conditions(data)
    
    async def _add_sensor_reading(self, reading: SensorReading):
        """Add a sensor reading to the fusion system"""
        sensor_readings = self.sensor_readings[reading.sensor_type]
        sensor_readings.append(reading)
        
        # Maintain history size limit
        if len(sensor_readings) > self.reading_history_size:
            sensor_readings.pop(0)
        
        # Update sensor reliability based on reading patterns
        await self._update_sensor_reliability(reading.sensor_type)
    
    async def _update_sensor_reliability(self, sensor_type: SensorType):
        """Update sensor reliability based on recent readings"""
        readings = self.sensor_readings[sensor_type]
        if len(readings) < 10:
            return
        
        recent_readings = readings[-10:]
        avg_confidence = statistics.mean([r.confidence for r in recent_readings])
        
        # Update reliability based on confidence and consistency
        if avg_confidence > 0.9:
            self.sensor_reliability[sensor_type] = SensorReliability.EXCELLENT
        elif avg_confidence > 0.8:
            self.sensor_reliability[sensor_type] = SensorReliability.GOOD
        elif avg_confidence > 0.6:
            self.sensor_reliability[sensor_type] = SensorReliability.FAIR
        elif avg_confidence > 0.3:
            self.sensor_reliability[sensor_type] = SensorReliability.POOR
        else:
            self.sensor_reliability[sensor_type] = SensorReliability.FAILED
    
    async def _update_environmental_conditions(self, data: Dict[str, Any]):
        """Update environmental conditions and adapt sensor weights"""
        self.environmental_conditions = EnvironmentalConditions(
            temperature=data.get('temperature', 20.0),
            humidity=data.get('humidity', 50.0),
            light_level=data.get('light_level', 1000.0),
            weather_condition=data.get('weather', 'clear'),
            wind_speed=data.get('wind_speed', 0.0),
            precipitation=data.get('precipitation', False),
            visibility_factor=self._calculate_visibility_factor(data)
        )
        
        if self.adaptive_weights_enabled:
            await self._adapt_sensor_weights()
    
    def _calculate_visibility_factor(self, env_data: Dict[str, Any]) -> float:
        """Calculate visibility factor based on environmental conditions"""
        base_visibility = 1.0
        
        # Reduce visibility based on weather conditions
        weather = env_data.get('weather', 'clear').lower()
        if weather in ['rain', 'heavy_rain']:
            base_visibility *= 0.6
        elif weather in ['fog', 'mist']:
            base_visibility *= 0.3
        elif weather in ['snow', 'heavy_snow']:
            base_visibility *= 0.4
        
        # Adjust for light level
        light_level = env_data.get('light_level', 1000.0)
        if light_level < 100:  # Very low light
            base_visibility *= 0.5
        elif light_level < 500:  # Low light
            base_visibility *= 0.8
        
        return max(0.1, base_visibility)  # Minimum 10% visibility
    
    async def _adapt_sensor_weights(self):
        """Adapt sensor weights based on environmental conditions"""
        if not self.environmental_conditions:
            return
        
        env = self.environmental_conditions
        new_weights = self.sensor_weights.copy()
        
        # Adjust camera weight based on visibility
        vision_factor = env.visibility_factor
        new_weights[SensorType.CAMERA_VISION] = 0.35 * vision_factor
        
        # Increase ToF weight when visibility is poor
        tof_boost = (1.0 - vision_factor) * 0.15
        new_weights[SensorType.TOF_LEFT] += tof_boost / 2
        new_weights[SensorType.TOF_RIGHT] += tof_boost / 2
        
        # Adjust for temperature effects on sensors
        if env.temperature < 0 or env.temperature > 35:
            # Reduce all sensor weights slightly in extreme temperatures
            for sensor_type in new_weights:
                new_weights[sensor_type] *= 0.95
        
        # Normalize weights to sum to 1.0
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            for sensor_type in new_weights:
                new_weights[sensor_type] /= total_weight
        
        self.sensor_weights = new_weights
        logger.debug(f"Adapted sensor weights: {self.sensor_weights}")
    
    async def _sensor_fusion_loop(self):
        """Main sensor fusion processing loop"""
        while self._running:
            try:
                start_time = datetime.now()
                
                # Perform sensor fusion
                fused_obstacles = await self._perform_sensor_fusion()
                
                # Process detected obstacles
                for obstacle in fused_obstacles:
                    await self._process_fused_obstacle(obstacle)
                
                # Update performance metrics
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                self.fusion_performance_metrics['response_time_ms'] = processing_time
                
                # Sleep for fusion rate
                await asyncio.sleep(self.fusion_window_ms / 1000.0)
                
            except Exception as e:
                logger.error(f"Error in sensor fusion loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _perform_sensor_fusion(self) -> List[FusedObstacleDetection]:
        """Perform multi-sensor fusion for obstacle detection"""
        current_time = datetime.now()
        fusion_window = timedelta(milliseconds=self.fusion_window_ms)
        cutoff_time = current_time - fusion_window
        
        # Get recent readings from all sensors
        recent_readings = {}
        for sensor_type, readings in self.sensor_readings.items():
            recent_readings[sensor_type] = [
                r for r in readings if r.timestamp > cutoff_time
            ]
        
        # Detect obstacles from each sensor
        sensor_obstacles = {}
        for sensor_type, readings in recent_readings.items():
            if readings:
                sensor_obstacles[sensor_type] = await self._detect_obstacles_from_sensor(
                    sensor_type, readings
                )
        
        # Fuse obstacle detections
        fused_obstacles = await self._fuse_obstacle_detections(sensor_obstacles)
        
        return fused_obstacles
    
    async def _detect_obstacles_from_sensor(self, sensor_type: SensorType, 
                                          readings: List[SensorReading]) -> List[Dict[str, Any]]:
        """Detect obstacles from a specific sensor type"""
        obstacles = []
        
        if sensor_type in [SensorType.TOF_LEFT, SensorType.TOF_RIGHT]:
            obstacles = await self._detect_tof_obstacles(sensor_type, readings)
        elif sensor_type == SensorType.CAMERA_VISION:
            obstacles = await self._detect_vision_obstacles(readings)
        elif sensor_type == SensorType.IMU:
            obstacles = await self._detect_imu_obstacles(readings)
        
        return obstacles
    
    async def _detect_tof_obstacles(self, sensor_type: SensorType, 
                                  readings: List[SensorReading]) -> List[Dict[str, Any]]:
        """Detect obstacles from ToF sensor readings"""
        obstacles = []
        
        for reading in readings:
            distance = reading.data.get('distance', float('inf'))
            if distance < 1.0:  # Obstacle within 1 meter
                # Determine position based on sensor type
                x_offset = -0.15 if sensor_type == SensorType.TOF_LEFT else 0.15
                
                obstacle = {
                    'position': (distance, x_offset, 0.0),
                    'size': (0.1, 0.1, 0.2),  # Estimated size
                    'confidence': reading.confidence,
                    'sensor_type': sensor_type,
                    'timestamp': reading.timestamp
                }
                obstacles.append(obstacle)
        
        return obstacles
    
    async def _detect_vision_obstacles(self, readings: List[SensorReading]) -> List[Dict[str, Any]]:
        """Detect obstacles from camera vision readings"""
        obstacles = []
        
        for reading in readings:
            detected_objects = reading.data.get('objects', [])
            for obj in detected_objects:
                obstacle = {
                    'position': (obj.get('distance', 1.0), obj.get('x_offset', 0.0), 0.0),
                    'size': (obj.get('width', 0.2), obj.get('height', 0.2), obj.get('depth', 0.2)),
                    'confidence': obj.get('confidence', 0.5) * reading.confidence,
                    'sensor_type': SensorType.CAMERA_VISION,
                    'timestamp': reading.timestamp,
                    'classification': obj.get('class', 'unknown')
                }
                obstacles.append(obstacle)
        
        return obstacles
    
    async def _detect_imu_obstacles(self, readings: List[SensorReading]) -> List[Dict[str, Any]]:
        """Detect obstacles from IMU readings (collision detection)"""
        obstacles = []
        
        # Look for sudden acceleration changes indicating collision
        if len(readings) >= 2:
            latest = readings[-1]
            previous = readings[-2]
            
            # Calculate acceleration magnitude change
            acc_latest = np.array([
                latest.data.get('acceleration_x', 0),
                latest.data.get('acceleration_y', 0),
                latest.data.get('acceleration_z', 0)
            ])
            acc_previous = np.array([
                previous.data.get('acceleration_x', 0),
                previous.data.get('acceleration_y', 0),
                previous.data.get('acceleration_z', 0)
            ])
            
            acc_change = np.linalg.norm(acc_latest - acc_previous)
            
            if acc_change > 2.0:  # Significant acceleration change
                obstacle = {
                    'position': (0.0, 0.0, 0.0),  # At mower location
                    'size': (0.5, 0.5, 0.5),  # Large area
                    'confidence': min(acc_change / 5.0, 1.0),
                    'sensor_type': SensorType.IMU,
                    'timestamp': latest.timestamp,
                    'classification': 'collision'
                }
                obstacles.append(obstacle)
        
        return obstacles
    
    async def _fuse_obstacle_detections(self, sensor_obstacles: Dict[SensorType, List[Dict[str, Any]]]) -> List[FusedObstacleDetection]:
        """Fuse obstacle detections from multiple sensors"""
        fused_obstacles = []
        
        # Collect all obstacle detections
        all_detections = []
        for sensor_type, obstacles in sensor_obstacles.items():
            for obstacle in obstacles:
                obstacle['sensor_type'] = sensor_type
                all_detections.append(obstacle)
        
        # Group nearby detections
        obstacle_groups = await self._group_nearby_detections(all_detections)
        
        # Create fused obstacles from groups
        for group in obstacle_groups:
            fused_obstacle = await self._create_fused_obstacle(group)
            if fused_obstacle.confidence >= self.confidence_threshold:
                fused_obstacles.append(fused_obstacle)
        
        return fused_obstacles
    
    async def _group_nearby_detections(self, detections: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group nearby obstacle detections"""
        groups = []
        ungrouped = detections.copy()
        
        while ungrouped:
            current = ungrouped.pop(0)
            group = [current]
            
            # Find nearby detections
            remaining = []
            for detection in ungrouped:
                distance = self._calculate_detection_distance(current, detection)
                if distance < 0.5:  # Within 50cm
                    group.append(detection)
                else:
                    remaining.append(detection)
            
            ungrouped = remaining
            groups.append(group)
        
        return groups
    
    def _calculate_detection_distance(self, det1: Dict[str, Any], det2: Dict[str, Any]) -> float:
        """Calculate distance between two detections"""
        pos1 = np.array(det1['position'])
        pos2 = np.array(det2['position'])
        return np.linalg.norm(pos1 - pos2)
    
    async def _create_fused_obstacle(self, detections: List[Dict[str, Any]]) -> FusedObstacleDetection:
        """Create a fused obstacle from grouped detections"""
        # Calculate weighted average position
        total_weight = 0
        weighted_position = np.array([0.0, 0.0, 0.0])
        weighted_size = np.array([0.0, 0.0, 0.0])
        
        contributing_sensors = []
        sensor_agreements = {}
        classifications = []
        
        for detection in detections:
            sensor_type = detection['sensor_type']
            weight = self.sensor_weights[sensor_type] * detection['confidence']
            total_weight += weight
            
            weighted_position += np.array(detection['position']) * weight
            weighted_size += np.array(detection['size']) * weight
            
            if sensor_type not in contributing_sensors:
                contributing_sensors.append(sensor_type)
            
            sensor_agreements[sensor_type] = detection['confidence']
            
            if 'classification' in detection:
                classifications.append(detection['classification'])
        
        if total_weight > 0:
            weighted_position /= total_weight
            weighted_size /= total_weight
        
        # Calculate overall confidence
        sensor_agreement = len(contributing_sensors) / len(SensorType)
        confidence = min(total_weight * sensor_agreement, 1.0)
        
        # Determine threat level
        threat_level = self._determine_threat_level(weighted_position, classifications)
        
        # Determine primary classification
        classification = max(set(classifications), key=classifications.count) if classifications else "unknown"
        
        obstacle_id = f"obstacle_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        return FusedObstacleDetection(
            obstacle_id=obstacle_id,
            position=tuple(weighted_position),
            size=tuple(weighted_size),
            confidence=confidence,
            threat_level=threat_level,
            contributing_sensors=contributing_sensors,
            sensor_agreements=sensor_agreements,
            classification=classification
        )
    
    def _determine_threat_level(self, position: np.ndarray, classifications: List[str]) -> HazardLevel:
        """Determine threat level based on position and classification"""
        distance = np.linalg.norm(position)
        
        # Critical threats
        if any(cls in ['person', 'pet', 'collision'] for cls in classifications):
            return HazardLevel.CRITICAL
        
        # High threats based on distance
        if distance < 0.2:
            return HazardLevel.CRITICAL
        elif distance < 0.5:
            return HazardLevel.HIGH
        elif distance < 1.0:
            return HazardLevel.MEDIUM
        else:
            return HazardLevel.LOW
    
    async def _process_fused_obstacle(self, obstacle: FusedObstacleDetection):
        """Process a fused obstacle detection"""
        # Update tracked obstacles
        self.tracked_obstacles[obstacle.obstacle_id] = obstacle
        
        # Trigger callbacks for obstacle detection
        for callback in self.obstacle_callbacks:
            try:
                await callback(obstacle)
            except Exception as e:
                logger.error(f"Error in obstacle callback: {e}")
        
        # Log obstacle detection
        logger.info(f"Fused obstacle detected: {obstacle.classification} at {obstacle.position} "
                   f"with confidence {obstacle.confidence:.2f} and threat level {obstacle.threat_level.value}")
    
    async def _obstacle_tracking_loop(self):
        """Track obstacles over time and remove stale ones"""
        while self._running:
            try:
                current_time = datetime.now()
                timeout_threshold = timedelta(seconds=self.obstacle_timeout_seconds)
                
                # Remove stale obstacles
                stale_obstacles = []
                for obstacle_id, obstacle in self.tracked_obstacles.items():
                    # Check if obstacle is stale (this is a simple implementation)
                    # In practice, you'd track the last seen time for each obstacle
                    stale_obstacles.append(obstacle_id)
                
                # For now, just clear all obstacles periodically to prevent memory buildup
                if len(self.tracked_obstacles) > 100:
                    oldest_obstacles = sorted(
                        self.tracked_obstacles.items(),
                        key=lambda x: x[0]  # Sort by obstacle_id which includes timestamp
                    )[:50]  # Keep only 50 newest
                    
                    for obstacle_id, _ in oldest_obstacles:
                        del self.tracked_obstacles[obstacle_id]
                
                await asyncio.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in obstacle tracking loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _environmental_monitoring_loop(self):
        """Monitor environmental conditions and adapt system"""
        while self._running:
            try:
                if self.environmental_conditions:
                    # Trigger environmental callbacks
                    for callback in self.environmental_callbacks:
                        try:
                            await callback(self.environmental_conditions)
                        except Exception as e:
                            logger.error(f"Error in environmental callback: {e}")
                
                await asyncio.sleep(5.0)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in environmental monitoring loop: {e}")
                await asyncio.sleep(5.0)
    
    def _calculate_tof_confidence(self, data: Dict[str, Any]) -> float:
        """Calculate confidence for ToF sensor reading"""
        distance = data.get('distance', float('inf'))
        signal_strength = data.get('signal_strength', 0)
        
        # Higher confidence for closer objects and stronger signals
        distance_factor = max(0.1, 1.0 - (distance / 3.0))  # Confidence decreases with distance
        signal_factor = min(signal_strength / 1000.0, 1.0)  # Normalize signal strength
        
        return min(distance_factor * signal_factor, 1.0)
    
    def _calculate_vision_confidence(self, data: Dict[str, Any]) -> float:
        """Calculate confidence for vision sensor reading"""
        objects = data.get('objects', [])
        if not objects:
            return 0.0
        
        # Average confidence of all detected objects
        confidences = [obj.get('confidence', 0.5) for obj in objects]
        return statistics.mean(confidences)
    
    def _calculate_imu_confidence(self, data: Dict[str, Any]) -> float:
        """Calculate confidence for IMU sensor reading"""
        # IMU confidence based on data validity and sensor status
        has_valid_data = all(
            key in data for key in ['acceleration_x', 'acceleration_y', 'acceleration_z']
        )
        
        if not has_valid_data:
            return 0.0
        
        # Check for reasonable acceleration values
        acc_values = [
            abs(data.get('acceleration_x', 0)),
            abs(data.get('acceleration_y', 0)),
            abs(data.get('acceleration_z', 0))
        ]
        
        # If accelerations are too high, sensor might be unreliable
        max_acc = max(acc_values)
        if max_acc > 10.0:  # More than 10g seems unrealistic
            return 0.3
        
        return 0.9  # Generally high confidence for IMU
    
    def register_obstacle_callback(self, callback: Callable):
        """Register callback for obstacle detection events"""
        self.obstacle_callbacks.append(callback)
    
    def register_environmental_callback(self, callback: Callable):
        """Register callback for environmental condition changes"""
        self.environmental_callbacks.append(callback)
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "sensor_reliability": {
                sensor_type.value: reliability.value 
                for sensor_type, reliability in self.sensor_reliability.items()
            },
            "sensor_weights": {
                sensor_type.value: weight 
                for sensor_type, weight in self.sensor_weights.items()
            },
            "environmental_conditions": {
                "temperature": self.environmental_conditions.temperature if self.environmental_conditions else None,
                "humidity": self.environmental_conditions.humidity if self.environmental_conditions else None,
                "visibility_factor": self.environmental_conditions.visibility_factor if self.environmental_conditions else None,
                "weather_condition": self.environmental_conditions.weather_condition if self.environmental_conditions else None
            },
            "tracked_obstacles": len(self.tracked_obstacles),
            "performance_metrics": self.fusion_performance_metrics,
            "adaptive_weights_enabled": self.adaptive_weights_enabled
        }
