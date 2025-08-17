"""
Obstacle detection system combining ToF sensors and computer vision
"""

import asyncio
import numpy as np
try:
    import cv2
except Exception:
    cv2 = None
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import logging
import uuid

from ..hardware.data_structures import ToFReading, CameraFrame
from ..communication import MQTTClient, MessageProtocol, SensorData
from .data_structures import (
    ObstacleInfo, ObstacleMap, ObstacleType, ObstacleData,
    PoseEstimate
)

logger = logging.getLogger(__name__)


class ObstacleDetectionSystem:
    """
    Obstacle detection system that combines ToF sensors and computer vision
    for comprehensive obstacle mapping and tracking
    """
    
    def __init__(self, mqtt_client: MQTTClient):
        self.mqtt_client = mqtt_client
        self.update_rate = 10  # Hz
        self.safety_update_rate = 20  # Hz for obstacle detection
        
        # Detection parameters
        self.min_detection_distance = 0.05  # 5cm minimum
        self.max_detection_distance = 5.0   # 5m maximum
        self.obstacle_confidence_threshold = 0.5
        self.safety_distance_threshold = 0.3  # 30cm safety margin
        
        # ToF sensor configuration
        self.tof_left_position = (-0.15, 0.2, 0.1)   # Left front position
        self.tof_right_position = (0.15, 0.2, 0.1)   # Right front position
        self.tof_max_range = 2.0  # meters
        
        # Current sensor data
        self._latest_tof_left: Optional[ToFReading] = None
        self._latest_tof_right: Optional[ToFReading] = None
        self._latest_camera_frame: Optional[CameraFrame] = None
        self._current_pose: Optional[PoseEstimate] = None
        
        # Obstacle tracking
        self._tracked_obstacles: Dict[str, ObstacleInfo] = {}
        self._obstacle_history: List[ObstacleMap] = []
        self._max_history_length = 50  # Keep last 5 seconds at 10Hz
        
        # Computer vision setup
        self._cv_enabled = True
        self._detection_model = None  # Would load actual model
        self._last_cv_processing_time = 0.0
        
        # Tasks
        self._detection_task: Optional[asyncio.Task] = None
        self._safety_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Performance metrics
        self._detection_count = 0
        self._false_positive_count = 0
        self._processing_times = []
        
    async def start(self):
        """Start the obstacle detection system"""
        logger.info("Starting obstacle detection system")
        self._running = True
        
        # Subscribe to sensor data
        await self._subscribe_to_sensors()
        
        # Initialize computer vision if available
        await self._initialize_computer_vision()
        
        # Start processing tasks
        self._detection_task = asyncio.create_task(self._detection_loop())
        self._safety_task = asyncio.create_task(self._safety_detection_loop())
        
    async def stop(self):
        """Stop the obstacle detection system"""
        logger.info("Stopping obstacle detection system")
        self._running = False
        
        if self._detection_task:
            self._detection_task.cancel()
            try:
                await self._detection_task
            except asyncio.CancelledError:
                pass
                
        if self._safety_task:
            self._safety_task.cancel()
            try:
                await self._safety_task
            except asyncio.CancelledError:
                pass
    
    async def _subscribe_to_sensors(self):
        """Subscribe to sensor data topics"""
        await self.mqtt_client.subscribe("lawnberry/sensors/tof_left", self._handle_tof_left_data)
        await self.mqtt_client.subscribe("lawnberry/sensors/tof_right", self._handle_tof_right_data)
        await self.mqtt_client.subscribe("lawnberry/sensors/camera", self._handle_camera_data)
        await self.mqtt_client.subscribe("lawnberry/sensors/localization", self._handle_pose_data)
    
    async def _handle_tof_left_data(self, topic: str, message: MessageProtocol):
        """Handle left ToF sensor data"""
        try:
            tof_data = message.payload
            self._latest_tof_left = ToFReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                sensor_id=tof_data.get('sensor_id', 'tof_left'),
                value=tof_data['distance_mm'],
                unit='mm',
                i2c_address=tof_data.get('i2c_address', 0x29),
                distance_mm=tof_data['distance_mm'],
                range_status=tof_data.get('range_status', 'valid')
            )
        except Exception as e:
            logger.error(f"Error processing left ToF data: {e}")
    
    async def _handle_tof_right_data(self, topic: str, message: MessageProtocol):
        """Handle right ToF sensor data"""
        try:
            tof_data = message.payload
            self._latest_tof_right = ToFReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                sensor_id=tof_data.get('sensor_id', 'tof_right'),
                value=tof_data['distance_mm'],
                unit='mm',
                i2c_address=tof_data.get('i2c_address', 0x30),
                distance_mm=tof_data['distance_mm'],
                range_status=tof_data.get('range_status', 'valid')
            )
        except Exception as e:
            logger.error(f"Error processing right ToF data: {e}")
    
    async def _handle_camera_data(self, topic: str, message: MessageProtocol):
        """Handle camera frame data"""
        try:
            camera_data = message.payload
            self._latest_camera_frame = CameraFrame(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                frame_id=camera_data['frame_id'],
                width=camera_data['width'],
                height=camera_data['height'],
                format=camera_data['format'],
                data=bytes(camera_data['data']),  # Would be base64 decoded
                metadata=camera_data.get('metadata', {})
            )
        except Exception as e:
            logger.error(f"Error processing camera data: {e}")
    
    async def _handle_pose_data(self, topic: str, message: MessageProtocol):
        """Handle pose estimation data"""
        try:
            pose_data = message.payload['pose']
            self._current_pose = PoseEstimate(
                timestamp=datetime.fromisoformat(pose_data['timestamp']),
                latitude=pose_data['latitude'],
                longitude=pose_data['longitude'],
                altitude=pose_data['altitude'],
                x=pose_data['x'],
                y=pose_data['y'],
                z=pose_data['z'],
                qw=pose_data['qw'],
                qx=pose_data['qx'],
                qy=pose_data['qy'],
                qz=pose_data['qz'],
                vx=pose_data['vx'],
                vy=pose_data['vy'],
                vz=pose_data['vz'],
                wx=pose_data['wx'],
                wy=pose_data['wy'],
                wz=pose_data['wz'],
                covariance=np.eye(6) * 0.1,  # Would parse actual covariance
                gps_accuracy=pose_data['gps_accuracy'],
                fusion_confidence=pose_data['fusion_confidence']
            )
        except Exception as e:
            logger.error(f"Error processing pose data: {e}")
    
    async def _initialize_computer_vision(self):
        """Initialize computer vision models"""
        try:
            # In real implementation, would load actual CV models
            # For now, simulate CV initialization
            self._cv_enabled = True
            logger.info("Computer vision initialized (simulated)")
        except Exception as e:
            logger.error(f"Failed to initialize computer vision: {e}")
            self._cv_enabled = False
    
    async def _detection_loop(self):
        """Main obstacle detection loop (10Hz)"""
        while self._running:
            try:
                start_time = datetime.now()
                
                # Process ToF sensor data
                tof_obstacles = await self._process_tof_sensors()
                
                # Process computer vision data
                cv_obstacles = await self._process_computer_vision()
                
                # Fuse detections
                fused_obstacles = await self._fuse_detections(tof_obstacles, cv_obstacles)
                
                # Update obstacle tracking
                await self._update_obstacle_tracking(fused_obstacles)
                
                # Generate obstacle map
                obstacle_map = self._generate_obstacle_map()
                
                # Publish obstacle data
                await self._publish_obstacle_data(obstacle_map)
                
                # Track performance
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                self._processing_times.append(processing_time)
                if len(self._processing_times) > 100:
                    self._processing_times.pop(0)
                
                await asyncio.sleep(1.0 / self.update_rate)
                
            except Exception as e:
                logger.error(f"Error in detection loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _safety_detection_loop(self):
        """Safety-critical obstacle detection (20Hz)"""
        while self._running:
            try:
                # Fast obstacle detection for immediate safety responses
                immediate_obstacles = await self._detect_immediate_hazards()
                
                if immediate_obstacles:
                    await self._publish_safety_alerts(immediate_obstacles)
                
                await asyncio.sleep(1.0 / self.safety_update_rate)
                
            except Exception as e:
                logger.error(f"Error in safety detection loop: {e}")
                await asyncio.sleep(0.05)
    
    async def _process_tof_sensors(self) -> List[ObstacleInfo]:
        """Process ToF sensor readings into obstacle information"""
        obstacles = []
        
        # Process left ToF sensor
        if (self._latest_tof_left and 
            self._latest_tof_left.range_status == 'valid' and
            self._latest_tof_left.distance_mm > 50):  # Minimum 5cm
            
            distance_m = self._latest_tof_left.distance_mm / 1000.0
            if distance_m <= self.tof_max_range:
                # Convert to robot-relative coordinates
                x = self.tof_left_position[0]
                y = self.tof_left_position[1] + distance_m
                z = self.tof_left_position[2]
                
                obstacle = ObstacleInfo(
                    obstacle_id=f"tof_left_{int(datetime.now().timestamp() * 1000)}",
                    obstacle_type=ObstacleType.UNKNOWN,
                    x=x, y=y, z=z,
                    width=0.1, height=0.1, depth=0.1,  # Assume small object
                    confidence=0.8,  # High confidence for ToF
                    detected_by=['tof_left'],
                    distance=distance_m
                )
                obstacles.append(obstacle)
        
        # Process right ToF sensor
        if (self._latest_tof_right and 
            self._latest_tof_right.range_status == 'valid' and
            self._latest_tof_right.distance_mm > 50):
            
            distance_m = self._latest_tof_right.distance_mm / 1000.0
            if distance_m <= self.tof_max_range:
                x = self.tof_right_position[0]
                y = self.tof_right_position[1] + distance_m
                z = self.tof_right_position[2]
                
                obstacle = ObstacleInfo(
                    obstacle_id=f"tof_right_{int(datetime.now().timestamp() * 1000)}",
                    obstacle_type=ObstacleType.UNKNOWN,
                    x=x, y=y, z=z,
                    width=0.1, height=0.1, depth=0.1,
                    confidence=0.8,
                    detected_by=['tof_right'],
                    distance=distance_m
                )
                obstacles.append(obstacle)
        
        return obstacles
    
    async def _process_computer_vision(self) -> List[ObstacleInfo]:
        """Process camera data for obstacle detection"""
        obstacles = []
        
        if not self._cv_enabled or not self._latest_camera_frame:
            return obstacles
        
        try:
            start_time = datetime.now()
            
            # Simulate computer vision processing
            # In real implementation, would use actual CV models
            detections = await self._simulate_cv_detection()
            
            for detection in detections:
                obstacle = ObstacleInfo(
                    obstacle_id=f"cv_{detection['id']}",
                    obstacle_type=ObstacleType(detection['type']),
                    x=detection['x'],
                    y=detection['y'],
                    z=detection['z'],
                    width=detection['width'],
                    height=detection['height'],
                    depth=detection['depth'],
                    confidence=detection['confidence'],
                    detected_by=['camera'],
                    distance=np.sqrt(detection['x']**2 + detection['y']**2 + detection['z']**2)
                )
                obstacles.append(obstacle)
            
            # Track processing time
            self._last_cv_processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
        except Exception as e:
            logger.error(f"Error in computer vision processing: {e}")
        
        return obstacles
    
    async def _simulate_cv_detection(self) -> List[Dict[str, Any]]:
        """Simulate computer vision detection results"""
        # In real implementation, this would run actual CV models
        detections = []
        
        # Simulate occasional detections
        import random
        if random.random() < 0.3:  # 30% chance of detection
            detection = {
                'id': str(uuid.uuid4())[:8],
                'type': random.choice(['unknown', 'static_object', 'vegetation']),
                'x': random.uniform(-1.0, 1.0),
                'y': random.uniform(0.5, 3.0),
                'z': random.uniform(-0.1, 0.5),
                'width': random.uniform(0.1, 0.5),
                'height': random.uniform(0.1, 0.5),
                'depth': random.uniform(0.1, 0.5),
                'confidence': random.uniform(0.6, 0.9)
            }
            detections.append(detection)
        
        return detections
    
    async def _fuse_detections(self, tof_obstacles: List[ObstacleInfo], 
                              cv_obstacles: List[ObstacleInfo]) -> List[ObstacleInfo]:
        """Fuse ToF and computer vision detections"""
        fused_obstacles = []
        
        # Start with all ToF obstacles (high confidence)
        fused_obstacles.extend(tof_obstacles)
        
        # Add CV obstacles that don't overlap with ToF
        for cv_obs in cv_obstacles:
            # Check if CV obstacle is close to any ToF obstacle
            overlaps = False
            for tof_obs in tof_obstacles:
                distance = np.sqrt((cv_obs.x - tof_obs.x)**2 + 
                                 (cv_obs.y - tof_obs.y)**2 + 
                                 (cv_obs.z - tof_obs.z)**2)
                if distance < 0.5:  # 50cm fusion threshold
                    # Merge detections - update ToF obstacle with CV information
                    tof_obs.obstacle_type = cv_obs.obstacle_type
                    tof_obs.width = max(tof_obs.width, cv_obs.width)
                    tof_obs.height = max(tof_obs.height, cv_obs.height)
                    tof_obs.depth = max(tof_obs.depth, cv_obs.depth)
                    tof_obs.detected_by.extend(cv_obs.detected_by)
                    tof_obs.confidence = min(1.0, tof_obs.confidence + cv_obs.confidence * 0.5)
                    overlaps = True
                    break
            
            if not overlaps:
                fused_obstacles.append(cv_obs)
        
        return fused_obstacles
    
    async def _update_obstacle_tracking(self, obstacles: List[ObstacleInfo]):
        """Update obstacle tracking with temporal consistency"""
        current_time = datetime.now()
        
        # Update existing tracked obstacles
        for obstacle in obstacles:
            # Try to match with existing tracked obstacles
            best_match = None
            best_distance = float('inf')
            
            for tracked_id, tracked_obs in self._tracked_obstacles.items():
                distance = np.sqrt((obstacle.x - tracked_obs.x)**2 + 
                                 (obstacle.y - tracked_obs.y)**2 + 
                                 (obstacle.z - tracked_obs.z)**2)
                
                if distance < 0.3 and distance < best_distance:  # 30cm matching threshold
                    best_match = tracked_id
                    best_distance = distance
            
            if best_match:
                # Update existing obstacle
                tracked_obs = self._tracked_obstacles[best_match]
                
                # Calculate velocity
                dt = (current_time - tracked_obs.last_updated).total_seconds()
                if dt > 0:
                    tracked_obs.vx = (obstacle.x - tracked_obs.x) / dt
                    tracked_obs.vy = (obstacle.y - tracked_obs.y) / dt
                    tracked_obs.vz = (obstacle.z - tracked_obs.z) / dt
                
                # Update position and properties
                tracked_obs.x = obstacle.x
                tracked_obs.y = obstacle.y
                tracked_obs.z = obstacle.z
                tracked_obs.obstacle_type = obstacle.obstacle_type
                tracked_obs.confidence = obstacle.confidence
                tracked_obs.detected_by = obstacle.detected_by
                tracked_obs.distance = obstacle.distance
                tracked_obs.last_updated = current_time
            else:
                # Add new obstacle
                obstacle.first_detected = current_time
                obstacle.last_updated = current_time
                self._tracked_obstacles[obstacle.obstacle_id] = obstacle
        
        # Remove old obstacles (not seen for more than 2 seconds)
        cutoff_time = current_time - timedelta(seconds=2)
        to_remove = [
            obs_id for obs_id, obs in self._tracked_obstacles.items()
            if obs.last_updated < cutoff_time
        ]
        
        for obs_id in to_remove:
            del self._tracked_obstacles[obs_id]
    
    def _generate_obstacle_map(self) -> ObstacleMap:
        """Generate obstacle map from tracked obstacles"""
        obstacles = list(self._tracked_obstacles.values())
        
        obstacle_map = ObstacleMap(
            timestamp=datetime.now(),
            obstacles=obstacles,
            map_radius=self.max_detection_distance,
            resolution=0.1
        )
        
        # Add to history
        self._obstacle_history.append(obstacle_map)
        if len(self._obstacle_history) > self._max_history_length:
            self._obstacle_history.pop(0)
        
        return obstacle_map
    
    async def _detect_immediate_hazards(self) -> List[ObstacleInfo]:
        """Detect immediate safety hazards that require emergency response"""
        hazards = []
        
        # Check ToF sensors for close obstacles
        if self._latest_tof_left and self._latest_tof_left.range_status == 'valid':
            distance_m = self._latest_tof_left.distance_mm / 1000.0
            if distance_m < self.safety_distance_threshold:
                hazard = ObstacleInfo(
                    obstacle_id=f"safety_left_{int(datetime.now().timestamp() * 1000)}",
                    obstacle_type=ObstacleType.UNKNOWN,
                    x=self.tof_left_position[0],
                    y=self.tof_left_position[1] + distance_m,
                    z=self.tof_left_position[2],
                    width=0.1, height=0.1, depth=0.1,
                    confidence=1.0,
                    detected_by=['tof_left'],
                    distance=distance_m
                )
                hazards.append(hazard)
        
        if self._latest_tof_right and self._latest_tof_right.range_status == 'valid':
            distance_m = self._latest_tof_right.distance_mm / 1000.0
            if distance_m < self.safety_distance_threshold:
                hazard = ObstacleInfo(
                    obstacle_id=f"safety_right_{int(datetime.now().timestamp() * 1000)}",
                    obstacle_type=ObstacleType.UNKNOWN,
                    x=self.tof_right_position[0],
                    y=self.tof_right_position[1] + distance_m,
                    z=self.tof_right_position[2],
                    width=0.1, height=0.1, depth=0.1,
                    confidence=1.0,
                    detected_by=['tof_right'],
                    distance=distance_m
                )
                hazards.append(hazard)
        
        return hazards
    
    async def _publish_safety_alerts(self, hazards: List[ObstacleInfo]):
        """Publish immediate safety alerts"""
        for hazard in hazards:
            alert_data = {
                'hazard_type': 'obstacle_proximity',
                'obstacle_id': hazard.obstacle_id,
                'distance': hazard.distance,
                'position': [hazard.x, hazard.y, hazard.z],
                'detected_by': hazard.detected_by,
                'timestamp': datetime.now().isoformat(),
                'immediate_response_required': True
            }
            
            message = SensorData.create(
                sender="obstacle_detection_system",
                sensor_type="safety_alert",
                data=alert_data
            )
            
            await self.mqtt_client.publish("lawnberry/safety/obstacle_alert", message)
    
    async def _publish_obstacle_data(self, obstacle_map: ObstacleMap):
        """Publish obstacle detection data"""
        # Prepare obstacle data
        obstacles_data = []
        for obstacle in obstacle_map.obstacles:
            obstacles_data.append({
                'obstacle_id': obstacle.obstacle_id,
                'type': obstacle.obstacle_type.value,
                'position': [obstacle.x, obstacle.y, obstacle.z],
                'size': [obstacle.width, obstacle.height, obstacle.depth],
                'velocity': [obstacle.vx, obstacle.vy, obstacle.vz],
                'distance': obstacle.distance,
                'confidence': obstacle.confidence,
                'detected_by': obstacle.detected_by,
                'first_detected': obstacle.first_detected.isoformat(),
                'last_updated': obstacle.last_updated.isoformat()
            })
        
        # Create obstacle data structure
        obstacle_data = ObstacleData(
            obstacle_map=obstacle_map,
            tof_left_distance=self._latest_tof_left.distance_mm / 1000.0 if self._latest_tof_left else 0.0,
            tof_right_distance=self._latest_tof_right.distance_mm / 1000.0 if self._latest_tof_right else 0.0,
            cv_detections=[],  # Would include actual CV detection details
            processing_time_ms=np.mean(self._processing_times) if self._processing_times else 0.0
        )
        
        # Prepare publishable data
        data = {
            'timestamp': obstacle_map.timestamp.isoformat(),
            'obstacles': obstacles_data,
            'total_obstacles': obstacle_map.total_obstacles,
            'high_confidence_obstacles': obstacle_map.high_confidence_obstacles,
            'dynamic_obstacles': obstacle_map.dynamic_obstacles,
            'tof_left_distance': obstacle_data.tof_left_distance,
            'tof_right_distance': obstacle_data.tof_right_distance,
            'processing_time_ms': obstacle_data.processing_time_ms,
            'detection_count': self._detection_count,
            'cv_enabled': self._cv_enabled
        }
        
        message = SensorData.create(
            sender="obstacle_detection_system",
            sensor_type="obstacles",
            data=data
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/obstacles", message)
        self._detection_count += 1
    
    def get_current_obstacles(self) -> List[ObstacleInfo]:
        """Get current tracked obstacles"""
        return list(self._tracked_obstacles.values())
    
    def get_obstacles_in_radius(self, radius: float) -> List[ObstacleInfo]:
        """Get obstacles within specified radius"""
        return [obs for obs in self._tracked_obstacles.values() if obs.distance <= radius]
    
    def get_nearest_obstacle_distance(self) -> float:
        """Get distance to nearest obstacle"""
        if not self._tracked_obstacles:
            return float('inf')
        
        return min(obs.distance for obs in self._tracked_obstacles.values())
    
    def get_processing_performance(self) -> Dict[str, float]:
        """Get processing performance metrics"""
        return {
            'average_processing_time_ms': np.mean(self._processing_times) if self._processing_times else 0.0,
            'max_processing_time_ms': np.max(self._processing_times) if self._processing_times else 0.0,
            'detection_rate_hz': self.update_rate,
            'cv_processing_time_ms': self._last_cv_processing_time,
            'tracked_obstacles_count': len(self._tracked_obstacles)
        }
