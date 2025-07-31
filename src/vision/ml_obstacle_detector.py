"""
Enhanced ML-based obstacle detection system for advanced safety
Integrates with existing ToF sensors and camera system
"""

import asyncio
import logging
import cv2
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
import json
import time
import threading
from collections import deque
from dataclasses import dataclass, field

from .data_structures import (
    DetectedObject, BoundingBox, ObjectType, SafetyLevel,
    VisionFrame, VisionConfig
)
from .object_detector import ObjectDetector
from .coral_tpu_manager import CoralTPUManager
from ..sensor_fusion.obstacle_detection import ObstacleDetectionSystem
from ..sensor_fusion.data_structures import ObstacleInfo, ObstacleType
from ..communication import MQTTClient, MessageProtocol


@dataclass
class MLDetectionResult:
    """Result from ML-based detection"""
    object_id: str
    object_type: str
    confidence: float
    bounding_box: BoundingBox
    distance: float
    safety_level: SafetyLevel
    motion_vector: Optional[Tuple[float, float]] = None
    trajectory_prediction: Optional[List[Tuple[float, float, float]]] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TemporalFilter:
    """Temporal filtering for reducing false positives"""
    detections: deque = field(default_factory=lambda: deque(maxlen=10))
    confidence_history: deque = field(default_factory=lambda: deque(maxlen=10))
    false_positive_count: int = 0
    confirmation_count: int = 0


class MLObstacleDetector:
    """Enhanced ML-based obstacle detection system"""
    
    def __init__(self, mqtt_client: MQTTClient, config: VisionConfig):
        self.logger = logging.getLogger(__name__)
        self.mqtt_client = mqtt_client
        self.config = config
        
        # Core components
        self.object_detector = ObjectDetector(config)
        self.tpu_manager = CoralTPUManager(config) if config.enable_tpu else None
        
        # ML model ensemble
        self._models = {
            'primary': None,
            'backup': None,
            'motion': None,
            'trajectory': None
        }
        self._model_weights = {
            'primary': 0.6,
            'backup': 0.3,
            'motion': 0.1
        }
        
        # Performance targets
        self.target_latency_ms = 100.0
        self.target_accuracy = 0.95
        self.max_false_positive_rate = 0.05
        
        # Detection tracking
        self._tracked_objects: Dict[str, MLDetectionResult] = {}
        self._temporal_filters: Dict[str, TemporalFilter] = {}
        self._detection_history: deque = deque(maxlen=100)
        
        # Motion and trajectory tracking
        self._motion_tracker = None
        self._trajectory_predictor = None
        
        # Performance metrics
        self._performance_stats = {
            'total_detections': 0,
            'true_positives': 0,
            'false_positives': 0,
            'false_negatives': 0,
            'processing_times': deque(maxlen=100),
            'accuracy': 0.0,
            'false_positive_rate': 0.0
        }
        
        # Safety integration
        self._safety_callbacks: List[callable] = []
        self._emergency_stop_triggered = False
        
        # Learning system
        self._learning_enabled = True
        self._training_data_buffer: deque = deque(maxlen=1000)
        self._adaptation_threshold = 0.1
        
        # Threading for real-time processing
        self._processing_thread: Optional[threading.Thread] = None
        self._frame_queue: deque = deque(maxlen=5)
        self._result_queue: deque = deque(maxlen=10)
        self._running = False
        
    async def initialize(self) -> bool:
        """Initialize the ML obstacle detection system"""
        try:
            self.logger.info("Initializing ML obstacle detection system")
            
            # Initialize core object detector
            if not await self.object_detector.initialize():
                self.logger.error("Failed to initialize object detector")
                return False
            
            # Load specialized models
            await self._load_specialized_models()
            
            # Initialize motion tracking
            await self._initialize_motion_tracking()
            
            # Initialize trajectory prediction
            await self._initialize_trajectory_prediction()
            
            # Start processing thread
            self._start_processing_thread()
            
            # Subscribe to safety system
            await self._subscribe_to_safety()
            
            self.logger.info("ML obstacle detection system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing ML obstacle detector: {e}")
            return False
    
    async def _load_specialized_models(self):
        """Load specialized ML models for different detection tasks"""
        try:
            # Load primary obstacle detection model
            if self.config.specialized_models.get('primary'):
                self._models['primary'] = await self._load_model(
                    self.config.specialized_models['primary']
                )
            
            # Load backup model
            if self.config.specialized_models.get('backup'):
                self._models['backup'] = await self._load_model(
                    self.config.specialized_models['backup']
                )
                
            # Load motion detection model
            if self.config.specialized_models.get('motion'):
                self._models['motion'] = await self._load_model(
                    self.config.specialized_models['motion']
                )
                
            self.logger.info("Specialized models loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Error loading specialized models: {e}")
    
    async def _load_model(self, model_path: str):
        """Load a specific ML model"""
        try:
            # Implementation would load actual model
            # For now, return a placeholder
            return {'path': model_path, 'loaded': True}
        except Exception as e:
            self.logger.error(f"Error loading model {model_path}: {e}")
            return None
    
    async def _initialize_motion_tracking(self):
        """Initialize motion tracking for moving objects"""
        try:
            # Initialize optical flow tracker
            self._motion_tracker = {
                'tracker': cv2.TrackerCSRT_create(),
                'last_frame': None,
                'tracked_points': []
            }
            
            self.logger.info("Motion tracking initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing motion tracking: {e}")
    
    async def _initialize_trajectory_prediction(self):
        """Initialize trajectory prediction for moving objects"""
        try:
            # Initialize Kalman filter for trajectory prediction
            self._trajectory_predictor = {
                'kalman_filters': {},
                'prediction_horizon': 2.0  # seconds
            }
            
            self.logger.info("Trajectory prediction initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing trajectory prediction: {e}")
    
    def _start_processing_thread(self):
        """Start the real-time processing thread"""
        self._running = True
        self._processing_thread = threading.Thread(
            target=self._processing_loop,
            daemon=True
        )
        self._processing_thread.start()
        self.logger.info("Processing thread started")
    
    def _processing_loop(self):
        """Main processing loop running in separate thread"""
        while self._running:
            try:
                if self._frame_queue:
                    frame = self._frame_queue.popleft()
                    result = asyncio.run(self._process_frame_sync(frame))
                    if result:
                        self._result_queue.append(result)
                else:
                    time.sleep(0.001)  # 1ms sleep when no frames
                    
            except Exception as e:
                self.logger.error(f"Error in processing loop: {e}")
                time.sleep(0.01)
    
    async def _process_frame_sync(self, vision_frame: VisionFrame) -> Optional[List[MLDetectionResult]]:
        """Process a single frame synchronously"""
        start_time = time.time()
        
        try:
            # Run ensemble detection
            detections = await self._run_ensemble_detection(vision_frame)
            
            # Apply temporal filtering
            filtered_detections = await self._apply_temporal_filtering(detections)
            
            # Update motion tracking
            motion_updated_detections = await self._update_motion_tracking(
                filtered_detections, vision_frame
            )
            
            # Predict trajectories
            trajectory_detections = await self._predict_trajectories(motion_updated_detections)
            
            # Update performance metrics
            processing_time = (time.time() - start_time) * 1000
            self._performance_stats['processing_times'].append(processing_time)
            
            # Check if we meet performance targets
            if processing_time > self.target_latency_ms:
                self.logger.warning(f"Processing time {processing_time:.1f}ms exceeds target {self.target_latency_ms}ms")
            
            return trajectory_detections
            
        except Exception as e:
            self.logger.error(f"Error processing frame: {e}")
            return None
    
    async def _run_ensemble_detection(self, vision_frame: VisionFrame) -> List[MLDetectionResult]:
        """Run ensemble detection using multiple models"""
        all_detections = []
        
        try:
            # Primary model detection
            if self._models['primary']:
                primary_detections = await self._run_model_detection(
                    vision_frame, self._models['primary'], 'primary'
                )
                all_detections.extend(primary_detections)
            
            # Backup model detection
            if self._models['backup']:
                backup_detections = await self._run_model_detection(
                    vision_frame, self._models['backup'], 'backup'
                )
                all_detections.extend(backup_detections)
            
            # Motion-specific detection
            if self._models['motion']:
                motion_detections = await self._run_motion_detection(vision_frame)
                all_detections.extend(motion_detections)
            
            # Ensemble fusion
            fused_detections = await self._fuse_ensemble_results(all_detections)
            
            return fused_detections
            
        except Exception as e:
            self.logger.error(f"Error in ensemble detection: {e}")
            return []
    
    async def _run_model_detection(self, vision_frame: VisionFrame, model: Dict, model_type: str) -> List[MLDetectionResult]:
        """Run detection on a specific model"""
        detections = []
        
        try:
            # Use existing object detector with the model
            detected_frame = await self.object_detector.detect_objects(vision_frame)
            
            # Convert to MLDetectionResult format
            for obj in detected_frame.detected_objects:
                detection = MLDetectionResult(
                    object_id=f"{model_type}_{obj.object_id}",
                    object_type=obj.type.value,
                    confidence=obj.confidence * self._model_weights.get(model_type, 1.0),
                    bounding_box=obj.bounding_box,
                    distance=obj.distance,
                    safety_level=obj.safety_level
                )
                detections.append(detection)
                
        except Exception as e:
            self.logger.error(f"Error running {model_type} model detection: {e}")
        
        return detections
    
    async def _run_motion_detection(self, vision_frame: VisionFrame) -> List[MLDetectionResult]:
        """Run motion-specific detection"""
        detections = []
        
        try:
            if not self._motion_tracker or not self._motion_tracker['last_frame']:
                # Store frame for next iteration
                frame = vision_frame.metadata.get('processed_frame')
                if frame is not None:
                    self._motion_tracker['last_frame'] = frame.copy()
                return detections
            
            current_frame = vision_frame.metadata.get('processed_frame')
            if current_frame is None:
                return detections
            
            # Calculate optical flow
            last_gray = cv2.cvtColor(self._motion_tracker['last_frame'], cv2.COLOR_BGR2GRAY)
            current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            
            # Detect motion areas
            flow = cv2.calcOpticalFlowPyrLK(
                last_gray, current_gray,
                np.array(self._motion_tracker['tracked_points'], dtype=np.float32),
                None
            )[0] if self._motion_tracker['tracked_points'] else None
            
            if flow is not None:
                # Process motion vectors to detect moving objects
                motion_areas = self._analyze_motion_vectors(flow, current_frame.shape)
                
                for area in motion_areas:
                    detection = MLDetectionResult(
                        object_id=f"motion_{area['id']}",
                        object_type="moving_object",
                        confidence=area['confidence'],
                        bounding_box=area['bounding_box'],
                        distance=area['distance'],
                        safety_level=SafetyLevel.HIGH,
                        motion_vector=area['motion_vector']
                    )
                    detections.append(detection)
            
            # Update last frame
            self._motion_tracker['last_frame'] = current_frame.copy()
            
        except Exception as e:
            self.logger.error(f"Error in motion detection: {e}")
        
        return detections
    
    def _analyze_motion_vectors(self, flow: np.ndarray, frame_shape: Tuple) -> List[Dict]:
        """Analyze motion vectors to identify moving objects"""
        motion_areas = []
        
        try:
            # Simplified motion analysis
            # In real implementation, would use more sophisticated algorithms
            if len(flow) > 0:
                motion_magnitude = np.linalg.norm(flow, axis=1)
                significant_motion = motion_magnitude > 5.0  # pixels per frame
                
                if np.any(significant_motion):
                    # Create bounding box around motion area
                    motion_points = flow[significant_motion]
                    if len(motion_points) > 0:
                        x_min, y_min = np.min(motion_points, axis=0)
                        x_max, y_max = np.max(motion_points, axis=0)
                        
                        area = {
                            'id': f"motion_{int(time.time() * 1000) % 10000}",
                            'confidence': min(1.0, len(motion_points) / 100.0),
                            'bounding_box': BoundingBox(
                                x1=int(x_min), y1=int(y_min),
                                x2=int(x_max), y2=int(y_max)
                            ),
                            'distance': 2.0,  # Estimated distance
                            'motion_vector': tuple(np.mean(motion_points, axis=0))
                        }
                        motion_areas.append(area)
                        
        except Exception as e:
            self.logger.error(f"Error analyzing motion vectors: {e}")
        
        return motion_areas
    
    async def _fuse_ensemble_results(self, all_detections: List[MLDetectionResult]) -> List[MLDetectionResult]:
        """Fuse results from multiple models"""
        if not all_detections:
            return []
        
        try:
            # Group detections by spatial proximity
            detection_groups = self._group_detections_by_proximity(all_detections)
            
            fused_detections = []
            for group in detection_groups:
                # Fuse detections in each group
                fused_detection = self._fuse_detection_group(group)
                if fused_detection:
                    fused_detections.append(fused_detection)
            
            return fused_detections
            
        except Exception as e:
            self.logger.error(f"Error fusing ensemble results: {e}")
            return all_detections
    
    def _group_detections_by_proximity(self, detections: List[MLDetectionResult]) -> List[List[MLDetectionResult]]:
        """Group detections that are spatially close"""
        groups = []
        used = set()
        
        for i, detection in enumerate(detections):
            if i in used:
                continue
                
            group = [detection]
            used.add(i)
            
            for j, other_detection in enumerate(detections[i+1:], i+1):
                if j in used:
                    continue
                    
                # Check if detections overlap
                if self._detections_overlap(detection, other_detection):
                    group.append(other_detection)
                    used.add(j)
            
            groups.append(group)
        
        return groups
    
    def _detections_overlap(self, det1: MLDetectionResult, det2: MLDetectionResult) -> bool:
        """Check if two detections overlap significantly"""
        try:
            # Calculate intersection over union (IoU)
            box1 = det1.bounding_box
            box2 = det2.bounding_box
            
            # Calculate intersection
            x1 = max(box1.x1, box2.x1)
            y1 = max(box1.y1, box2.y1)
            x2 = min(box1.x2, box2.x2)
            y2 = min(box1.y2, box2.y2)
            
            if x2 <= x1 or y2 <= y1:
                return False
            
            intersection = (x2 - x1) * (y2 - y1)
            area1 = (box1.x2 - box1.x1) * (box1.y2 - box1.y1)
            area2 = (box2.x2 - box2.x1) * (box2.y2 - box2.y1)
            union = area1 + area2 - intersection
            
            iou = intersection / union if union > 0 else 0
            return iou > 0.3  # 30% overlap threshold
            
        except Exception as e:
            self.logger.error(f"Error checking detection overlap: {e}")
            return False
    
    def _fuse_detection_group(self, group: List[MLDetectionResult]) -> Optional[MLDetectionResult]:
        """Fuse a group of detections into a single detection"""
        if not group:
            return None
        
        if len(group) == 1:
            return group[0]
        
        try:
            # Weighted average based on confidence
            total_confidence = sum(det.confidence for det in group)
            if total_confidence == 0:
                return group[0]
            
            # Calculate weighted bounding box
            weighted_x1 = sum(det.bounding_box.x1 * det.confidence for det in group) / total_confidence
            weighted_y1 = sum(det.bounding_box.y1 * det.confidence for det in group) / total_confidence
            weighted_x2 = sum(det.bounding_box.x2 * det.confidence for det in group) / total_confidence
            weighted_y2 = sum(det.bounding_box.y2 * det.confidence for det in group) / total_confidence
            
            # Calculate weighted distance
            weighted_distance = sum(det.distance * det.confidence for det in group) / total_confidence
            
            # Take highest confidence detection as base
            best_detection = max(group, key=lambda x: x.confidence)
            
            # Create fused detection
            fused_detection = MLDetectionResult(
                object_id=f"fused_{best_detection.object_id}",
                object_type=best_detection.object_type,
                confidence=min(1.0, total_confidence / len(group)),
                bounding_box=BoundingBox(
                    x1=int(weighted_x1), y1=int(weighted_y1),
                    x2=int(weighted_x2), y2=int(weighted_y2)
                ),
                distance=weighted_distance,
                safety_level=max(det.safety_level for det in group),
                motion_vector=best_detection.motion_vector,
                trajectory_prediction=best_detection.trajectory_prediction
            )
            
            return fused_detection
            
        except Exception as e:
            self.logger.error(f"Error fusing detection group: {e}")
            return group[0]
    
    async def _apply_temporal_filtering(self, detections: List[MLDetectionResult]) -> List[MLDetectionResult]:
        """Apply temporal filtering to reduce false positives"""
        filtered_detections = []
        
        try:
            for detection in detections:
                # Get or create temporal filter for this object type
                filter_key = f"{detection.object_type}_{detection.bounding_box.x1}_{detection.bounding_box.y1}"
                
                if filter_key not in self._temporal_filters:
                    self._temporal_filters[filter_key] = TemporalFilter()
                
                temp_filter = self._temporal_filters[filter_key]
                
                # Add current detection to filter
                temp_filter.detections.append(detection)
                temp_filter.confidence_history.append(detection.confidence)
                
                # Calculate temporal consistency
                if len(temp_filter.confidence_history) >= 3:
                    avg_confidence = np.mean(temp_filter.confidence_history)
                    confidence_std = np.std(temp_filter.confidence_history)
                    
                    # Check for consistent detection
                    if avg_confidence > 0.6 and confidence_std < 0.3:
                        temp_filter.confirmation_count += 1
                        
                        # Confirmed detection - add to results
                        if temp_filter.confirmation_count >= 2:
                            # Update confidence based on temporal consistency
                            detection.confidence = min(1.0, avg_confidence * 1.1)
                            filtered_detections.append(detection)
                    else:
                        temp_filter.false_positive_count += 1
                
                # Clean up old filters
                if len(self._temporal_filters) > 100:
                    self._cleanup_temporal_filters()
            
            return filtered_detections
            
        except Exception as e:
            self.logger.error(f"Error applying temporal filtering: {e}")
            return detections
    
    def _cleanup_temporal_filters(self):
        """Clean up old temporal filters"""
        try:
            # Remove filters that haven't been updated recently
            current_time = datetime.now()
            to_remove = []
            
            for key, temp_filter in self._temporal_filters.items():
                if temp_filter.detections:
                    last_detection = temp_filter.detections[-1]
                    if (current_time - last_detection.timestamp).total_seconds() > 10.0:
                        to_remove.append(key)
            
            for key in to_remove:
                del self._temporal_filters[key]
                
        except Exception as e:
            self.logger.error(f"Error cleaning up temporal filters: {e}")
    
    async def _update_motion_tracking(self, detections: List[MLDetectionResult], 
                                    vision_frame: VisionFrame) -> List[MLDetectionResult]:
        """Update motion tracking for detected objects"""
        try:
            updated_detections = []
            
            for detection in detections:
                # Update motion vector if not already set
                if not detection.motion_vector and detection.object_id in self._tracked_objects:
                    prev_detection = self._tracked_objects[detection.object_id]
                    
                    # Calculate motion vector
                    dt = (detection.timestamp - prev_detection.timestamp).total_seconds()
                    if dt > 0:
                        dx = detection.bounding_box.x1 - prev_detection.bounding_box.x1
                        dy = detection.bounding_box.y1 - prev_detection.bounding_box.y1
                        
                        detection.motion_vector = (dx / dt, dy / dt)
                
                # Store for next iteration
                self._tracked_objects[detection.object_id] = detection
                updated_detections.append(detection)
            
            return updated_detections
            
        except Exception as e:
            self.logger.error(f"Error updating motion tracking: {e}")
            return detections
    
    async def _predict_trajectories(self, detections: List[MLDetectionResult]) -> List[MLDetectionResult]:
        """Predict trajectories for moving objects"""
        try:
            for detection in detections:
                if detection.motion_vector and not detection.trajectory_prediction:
                    # Simple linear trajectory prediction
                    vx, vy = detection.motion_vector
                    current_x = detection.bounding_box.x1 + (detection.bounding_box.x2 - detection.bounding_box.x1) / 2
                    current_y = detection.bounding_box.y1 + (detection.bounding_box.y2 - detection.bounding_box.y1) / 2
                    
                    trajectory = []
                    for t in [0.5, 1.0, 1.5, 2.0]:  # Predict 0.5, 1, 1.5, 2 seconds ahead
                        future_x = current_x + vx * t
                        future_y = current_y + vy * t
                        trajectory.append((future_x, future_y, t))
                    
                    detection.trajectory_prediction = trajectory
            
            return detections
            
        except Exception as e:
            self.logger.error(f"Error predicting trajectories: {e}")
            return detections
    
    async def detect_obstacles(self, vision_frame: VisionFrame) -> List[MLDetectionResult]:
        """Main entry point for ML obstacle detection"""
        try:
            # Add frame to processing queue
            if len(self._frame_queue) < 5:  # Prevent queue overflow
                self._frame_queue.append(vision_frame)
            
            # Get latest results
            results = []
            while self._result_queue:
                results = self._result_queue.popleft()
            
            # Update performance metrics
            if results:
                self._update_performance_metrics(results)
                
                # Check for safety-critical objects
                await self._check_safety_critical_objects(results)
            
            return results or []
            
        except Exception as e:
            self.logger.error(f"Error in ML obstacle detection: {e}")
            return []
    
    def _update_performance_metrics(self, results: List[MLDetectionResult]):
        """Update performance metrics"""
        try:
            self._performance_stats['total_detections'] += len(results)
            
            # Calculate accuracy (simplified - would need ground truth in real implementation)
            high_confidence_detections = sum(1 for r in results if r.confidence > 0.8)
            self._performance_stats['true_positives'] += high_confidence_detections
            
            # Estimate false positives (detections with low confidence or inconsistent history)
            low_confidence_detections = sum(1 for r in results if r.confidence < 0.5)
            self._performance_stats['false_positives'] += low_confidence_detections
            
            # Update accuracy calculation
            total_positive = (self._performance_stats['true_positives'] + 
                            self._performance_stats['false_positives'])
            if total_positive > 0:
                self._performance_stats['accuracy'] = (
                    self._performance_stats['true_positives'] / total_positive
                )
                self._performance_stats['false_positive_rate'] = (
                    self._performance_stats['false_positives'] / total_positive
                )
            
        except Exception as e:
            self.logger.error(f"Error updating performance metrics: {e}")
    
    async def _check_safety_critical_objects(self, results: List[MLDetectionResult]):
        """Check for safety-critical objects and trigger appropriate responses"""
        try:
            critical_objects = [r for r in results if r.safety_level == SafetyLevel.CRITICAL]
            high_priority_objects = [r for r in results if r.safety_level == SafetyLevel.HIGH]
            
            if critical_objects:
                await self._trigger_emergency_response(critical_objects)
            elif high_priority_objects:
                await self._trigger_high_priority_response(high_priority_objects)
                
        except Exception as e:
            self.logger.error(f"Error checking safety-critical objects: {e}")
    
    async def _trigger_emergency_response(self, critical_objects: List[MLDetectionResult]):
        """Trigger emergency response for critical objects"""
        try:
            if not self._emergency_stop_triggered:
                self._emergency_stop_triggered = True
                
                # Publish emergency stop
                await self.mqtt_client.publish(
                    "lawnberry/safety/emergency_stop",
                    {
                        "trigger": "ml_obstacle_detection",
                        "objects": [
                            {
                                "type": obj.object_type,
                                "confidence": obj.confidence,
                                "distance": obj.distance,
                                "safety_level": obj.safety_level.value
                            }
                            for obj in critical_objects
                        ],
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                # Call safety callbacks
                for callback in self._safety_callbacks:
                    try:
                        await callback("emergency_stop", critical_objects)
                    except Exception as e:
                        self.logger.error(f"Error in safety callback: {e}")
                
                self.logger.critical(f"Emergency stop triggered by ML detection: {len(critical_objects)} critical objects")
                
        except Exception as e:
            self.logger.error(f"Error triggering emergency response: {e}")
    
    async def _trigger_high_priority_response(self, high_priority_objects: List[MLDetectionResult]):
        """Trigger high priority response for high priority objects"""
        try:
            # Publish high priority alert
            await self.mqtt_client.publish(
                "lawnberry/safety/high_priority_alert",
                {
                    "trigger": "ml_obstacle_detection",
                    "objects": [
                        {
                            "type": obj.object_type,
                            "confidence": obj.confidence,
                            "distance": obj.distance,
                            "motion_vector": obj.motion_vector,
                            "trajectory": obj.trajectory_prediction
                        }
                        for obj in high_priority_objects
                    ],
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            self.logger.warning(f"High priority alert: {len(high_priority_objects)} objects detected")
            
        except Exception as e:
            self.logger.error(f"Error triggering high priority response: {e}")
    
    async def _subscribe_to_safety(self):
        """Subscribe to safety system topics"""
        try:
            # Subscribe to safety system status
            await self.mqtt_client.subscribe(
                "lawnberry/safety/status",
                self._handle_safety_status
            )
            
            # Subscribe to system reset
            await self.mqtt_client.subscribe(
                "lawnberry/system/reset",
                self._handle_system_reset
            )
            
        except Exception as e:
            self.logger.error(f"Error subscribing to safety topics: {e}")
    
    async def _handle_safety_status(self, topic: str, message: MessageProtocol):
        """Handle safety system status updates"""
        try:
            status = message.payload.get('status')
            if status == 'normal':
                self._emergency_stop_triggered = False
                
        except Exception as e:
            self.logger.error(f"Error handling safety status: {e}")
    
    async def _handle_system_reset(self, topic: str, message: MessageProtocol):
        """Handle system reset"""
        try:
            self._emergency_stop_triggered = False
            self._tracked_objects.clear()
            self._temporal_filters.clear()
            
        except Exception as e:
            self.logger.error(f"Error handling system reset: {e}")
    
    def register_safety_callback(self, callback: callable):
        """Register a safety callback function"""
        self._safety_callbacks.append(callback)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        stats = self._performance_stats.copy()
        
        # Add latency statistics
        if stats['processing_times']:
            stats['avg_latency_ms'] = np.mean(stats['processing_times'])
            stats['max_latency_ms'] = np.max(stats['processing_times'])
            stats['min_latency_ms'] = np.min(stats['processing_times'])
        
        # Add targets comparison
        stats['meets_accuracy_target'] = stats['accuracy'] >= self.target_accuracy
        stats['meets_false_positive_target'] = stats['false_positive_rate'] <= self.max_false_positive_rate
        stats['meets_latency_target'] = (
            stats.get('avg_latency_ms', float('inf')) <= self.target_latency_ms
        )
        
        return stats
    
    async def shutdown(self):
        """Shutdown the ML obstacle detection system"""
        try:
            self.logger.info("Shutting down ML obstacle detection system")
            
            # Stop processing thread
            self._running = False
            if self._processing_thread:
                self._processing_thread.join(timeout=2.0)
            
            # Cleanup resources
            self._tracked_objects.clear()
            self._temporal_filters.clear()
            self._frame_queue.clear()
            self._result_queue.clear()
            
            self.logger.info("ML obstacle detection system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
