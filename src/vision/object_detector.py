"""Object detection and classification using AI models"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .coral_tpu_manager import CoralTPUManager, CPUFallbackManager
from .data_structures import (
    SAFETY_LEVELS,
    BoundingBox,
    DetectedObject,
    ObjectType,
    SafetyLevel,
    VisionConfig,
    VisionFrame,
)


class ObjectDetector:
    """AI-powered object detection and classification"""

    def __init__(self, config: VisionConfig):
        self.logger = logging.getLogger(__name__)
        self.config = config

        # AI model managers
        self.tpu_manager = CoralTPUManager(config) if config.enable_tpu else None
        self.cpu_manager = CPUFallbackManager(config) if config.fallback_to_cpu else None

        # Model state
        self._model_loaded = False
        self._current_model_path = None

        # Class mapping (COCO classes to our object types)
        self._class_mapping = self._load_class_mapping()

        # Performance tracking
        self._detection_stats = {
            "total_detections": 0,
            "successful_detections": 0,
            "false_positives": 0,
            "processing_times": [],
        }

    async def initialize(self) -> bool:
        """Initialize object detection system"""
        try:
            # Try to initialize TPU first
            if self.tpu_manager:
                success = await self.tpu_manager.initialize(self.config.primary_model_path)
                if success:
                    self._model_loaded = True
                    self._current_model_path = self.config.primary_model_path
                    self.logger.info("Object detector initialized with Coral TPU")
                    return True

            # Fall back to CPU if TPU fails or is disabled
            if self.cpu_manager:
                success = await self.cpu_manager.initialize(self.config.backup_model_path)
                if success:
                    self._model_loaded = True
                    self._current_model_path = self.config.backup_model_path
                    self.logger.info("Object detector initialized with CPU fallback")
                    return True

            self.logger.error("Failed to initialize any detection backend")
            return False

        except Exception as e:
            self.logger.error(f"Error initializing object detector: {e}")
            return False

    async def detect_objects(self, vision_frame: VisionFrame) -> VisionFrame:
        """Detect and classify objects in a vision frame"""
        if not self._model_loaded:
            self.logger.warning("Object detector not initialized")
            return vision_frame

        start_time = time.time()

        try:
            # Get the processed frame from metadata
            frame = vision_frame.metadata.get("processed_frame")
            if frame is None:
                self.logger.error("No processed frame available for detection")
                return vision_frame

            # Run inference
            inference_result = None
            tpu_used = False

            if self.tpu_manager and self.tpu_manager.is_available():
                inference_result = await self.tpu_manager.run_inference(frame)
                tpu_used = True
            elif self.cpu_manager and self.cpu_manager.is_available():
                inference_result = await self.cpu_manager.run_inference(frame)
                tpu_used = False

            if not inference_result:
                self.logger.warning("Inference failed on all backends")
                return vision_frame

            # Parse inference results into detections
            raw_detections = self._parse_inference_results(inference_result)

            # Convert to DetectedObject instances
            detected_objects = await self._process_detections(
                raw_detections, vision_frame.width, vision_frame.height
            )

            # Apply non-maximum suppression
            filtered_objects = self._apply_nms(detected_objects)

            # Update vision frame
            vision_frame.objects = filtered_objects
            vision_frame.tpu_used = tpu_used
            vision_frame.model_version = self._current_model_path

            # Calculate processing time
            processing_time = (time.time() - start_time) * 1000
            vision_frame.processing_time_ms += processing_time

            # Update statistics
            self._update_detection_stats(len(filtered_objects), processing_time)

            return vision_frame

        except Exception as e:
            self.logger.error(f"Error during object detection: {e}")
            return vision_frame

    def _parse_inference_results(self, inference_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse raw inference results"""
        try:
            if self.tpu_manager and inference_result.get("tpu_used", False):
                return self.tpu_manager.parse_detection_results(
                    inference_result, self.config.confidence_threshold
                )
            else:
                # Parse CPU results (similar logic but adapted for CPU format)
                return self._parse_cpu_results(inference_result)

        except Exception as e:
            self.logger.error(f"Error parsing inference results: {e}")
            return []

    def _parse_cpu_results(self, inference_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse CPU inference results"""
        # Implementation would depend on the specific CPU model format
        # This is a placeholder that should be implemented based on the actual model
        return []

    async def _process_detections(
        self, raw_detections: List[Dict[str, Any]], frame_width: int, frame_height: int
    ) -> List[DetectedObject]:
        """Convert raw detections to DetectedObject instances"""
        detected_objects = []

        for detection in raw_detections:
            try:
                # Extract bounding box (assume normalized coordinates)
                bbox_data = detection["bbox"]
                x = int(bbox_data["x"] * frame_width)
                y = int(bbox_data["y"] * frame_height)
                width = int(bbox_data["width"] * frame_width)
                height = int(bbox_data["height"] * frame_height)

                # Ensure bounding box is within frame
                x = max(0, min(x, frame_width - 1))
                y = max(0, min(y, frame_height - 1))
                width = max(1, min(width, frame_width - x))
                height = max(1, min(height, frame_height - y))

                bbox = BoundingBox(
                    x=x, y=y, width=width, height=height, confidence=detection["confidence"]
                )

                # Map class ID to object type
                class_id = detection.get("class_id", 0)
                object_type = self._map_class_to_object_type(class_id)

                # Determine safety level
                safety_level = SAFETY_LEVELS.get(object_type, SafetyLevel.MEDIUM)

                # Estimate distance (placeholder - would need depth info or size-based estimation)
                distance_estimate = self._estimate_distance(bbox, object_type)

                detected_object = DetectedObject(
                    object_type=object_type,
                    bounding_box=bbox,
                    confidence=detection["confidence"],
                    safety_level=safety_level,
                    distance_estimate=distance_estimate,
                    metadata={
                        "class_id": class_id,
                        "detection_time": time.time(),
                        "frame_area_ratio": bbox.area / (frame_width * frame_height),
                    },
                )

                detected_objects.append(detected_object)

            except Exception as e:
                self.logger.error(f"Error processing detection: {e}")
                continue

        return detected_objects

    def _apply_nms(self, detections: List[DetectedObject]) -> List[DetectedObject]:
        """Apply Non-Maximum Suppression to remove duplicate detections"""
        if len(detections) <= 1:
            return detections

        try:
            # Convert to format suitable for OpenCV NMS
            boxes = []
            scores = []

            for det in detections:
                bbox = det.bounding_box
                boxes.append([bbox.x, bbox.y, bbox.x + bbox.width, bbox.y + bbox.height])
                scores.append(det.confidence)

            boxes = np.array(boxes, dtype=np.float32)
            scores = np.array(scores, dtype=np.float32)

            # Apply NMS
            indices = cv2.dnn.NMSBoxes(
                boxes.tolist(),
                scores.tolist(),
                self.config.confidence_threshold,
                self.config.nms_threshold,
            )

            if len(indices) > 0:
                indices = indices.flatten()
                return [detections[i] for i in indices]
            else:
                return []

        except Exception as e:
            self.logger.error(f"Error applying NMS: {e}")
            return detections

    def _map_class_to_object_type(self, class_id: int) -> ObjectType:
        """Map model class ID to our ObjectType enum"""
        return self._class_mapping.get(class_id, ObjectType.UNKNOWN)

    def _estimate_distance(self, bbox: BoundingBox, object_type: ObjectType) -> Optional[float]:
        """Estimate distance to object based on bounding box size and type"""
        try:
            # This is a simplified distance estimation
            # In practice, this would use camera calibration, stereo vision, or ToF sensor data

            # Known approximate sizes for different object types (in meters)
            typical_sizes = {
                ObjectType.PERSON: 1.7,  # height
                ObjectType.PET: 0.5,  # height
                ObjectType.TOY: 0.2,  # diameter
                ObjectType.FURNITURE: 1.0,  # width
                ObjectType.TREE: 2.0,  # width
                ObjectType.STONE: 0.3,  # diameter
            }

            if object_type not in typical_sizes:
                return None

            # Simple pinhole camera model estimation
            # distance = (focal_length * real_size) / pixel_size
            # This is very approximate and should be calibrated
            focal_length_pixels = 800  # Approximate for typical camera
            real_size = typical_sizes[object_type]
            pixel_size = max(bbox.width, bbox.height)

            if pixel_size > 0:
                distance = (focal_length_pixels * real_size) / pixel_size
                return max(0.1, min(distance, 50.0))  # Clamp to reasonable range

            return None

        except Exception as e:
            self.logger.error(f"Error estimating distance: {e}")
            return None

    def _load_class_mapping(self) -> Dict[int, ObjectType]:
        """Load class ID to ObjectType mapping"""
        # COCO class mapping (simplified)
        # In practice, this might be loaded from a configuration file
        return {
            0: ObjectType.PERSON,  # person
            15: ObjectType.PET,  # cat
            16: ObjectType.PET,  # dog
            17: ObjectType.PET,  # horse
            32: ObjectType.TOY,  # sports ball
            37: ObjectType.TOY,  # frisbee
            38: ObjectType.TOY,  # kite
            56: ObjectType.FURNITURE,  # chair
            57: ObjectType.FURNITURE,  # couch
            58: ObjectType.FURNITURE,  # potted plant
            59: ObjectType.FURNITURE,  # bed
            60: ObjectType.FURNITURE,  # dining table
            62: ObjectType.FURNITURE,  # tv
            # Add more mappings as needed
        }

    def _update_detection_stats(self, detection_count: int, processing_time: float):
        """Update detection performance statistics"""
        self._detection_stats["total_detections"] += detection_count
        self._detection_stats["successful_detections"] += 1
        self._detection_stats["processing_times"].append(processing_time)

        # Keep only recent processing times
        if len(self._detection_stats["processing_times"]) > 100:
            self._detection_stats["processing_times"].pop(0)

    async def classify_surface_conditions(self, frame: np.ndarray) -> Dict[str, Any]:
        """Classify surface conditions (holes, slopes, wet areas)"""
        try:
            # Convert to grayscale for analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Detect holes using contour detection
            holes_detected = await self._detect_holes(gray)

            # Detect slopes using gradient analysis
            slopes_detected = await self._detect_slopes(gray)

            # Detect wet areas using color/texture analysis
            wet_areas_detected = await self._detect_wet_areas(frame)

            return {
                "holes": holes_detected,
                "slopes": slopes_detected,
                "wet_areas": wet_areas_detected,
                "surface_safe": not (holes_detected or slopes_detected or wet_areas_detected),
            }

        except Exception as e:
            self.logger.error(f"Error analyzing surface conditions: {e}")
            return {"holes": False, "slopes": False, "wet_areas": False, "surface_safe": True}

    async def _detect_holes(self, gray_frame: np.ndarray) -> bool:
        """Detect holes in the surface"""
        try:
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray_frame, (5, 5), 0)

            # Use adaptive threshold to find dark regions
            thresh = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

            # Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Check for dark circular regions that might be holes
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > 100:  # Minimum hole size
                    # Check if contour is roughly circular
                    perimeter = cv2.arcLength(contour, True)
                    if perimeter > 0:
                        circularity = 4 * np.pi * area / (perimeter * perimeter)
                        if circularity > 0.5:  # Reasonably circular
                            return True

            return False

        except Exception as e:
            self.logger.error(f"Error detecting holes: {e}")
            return False

    async def _detect_slopes(self, gray_frame: np.ndarray) -> bool:
        """Detect significant slopes in the terrain"""
        try:
            # Calculate gradients
            grad_x = cv2.Sobel(gray_frame, cv2.CV_64F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray_frame, cv2.CV_64F, 0, 1, ksize=3)

            # Calculate gradient magnitude
            gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)

            # Check if gradient exceeds threshold (indicating steep slope)
            steep_threshold = np.percentile(gradient_magnitude, 95)  # Top 5% of gradients
            steep_areas = gradient_magnitude > steep_threshold

            # Check if steep areas cover significant portion of frame
            steep_ratio = np.sum(steep_areas) / steep_areas.size

            return steep_ratio > 0.1  # More than 10% of frame is steep

        except Exception as e:
            self.logger.error(f"Error detecting slopes: {e}")
            return False

    async def _detect_wet_areas(self, frame: np.ndarray) -> bool:
        """Detect wet areas on the lawn"""
        try:
            # Convert to HSV for better color analysis
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            # Wet grass typically has different saturation and value
            # This is a simplified approach - could be improved with ML

            # Define range for wet grass (darker, more saturated greens)
            lower_wet = np.array([40, 50, 20])  # Lower HSV values for wet grass
            upper_wet = np.array([80, 255, 100])  # Upper HSV values for wet grass

            # Create mask for wet areas
            wet_mask = cv2.inRange(hsv, lower_wet, upper_wet)

            # Check if wet areas cover significant portion
            wet_ratio = np.sum(wet_mask > 0) / wet_mask.size

            return wet_ratio > 0.15  # More than 15% appears wet

        except Exception as e:
            self.logger.error(f"Error detecting wet areas: {e}")
            return False

    def get_detection_stats(self) -> Dict[str, Any]:
        """Get object detection performance statistics"""
        avg_processing_time = 0.0
        if self._detection_stats["processing_times"]:
            avg_processing_time = sum(self._detection_stats["processing_times"]) / len(
                self._detection_stats["processing_times"]
            )

        # Get TPU stats if available
        tpu_stats = {}
        if self.tpu_manager:
            tpu_stats = self.tpu_manager.get_performance_stats()

        return {
            "model_loaded": self._model_loaded,
            "current_model": self._current_model_path,
            "total_detections": self._detection_stats["total_detections"],
            "successful_detections": self._detection_stats["successful_detections"],
            "average_processing_time_ms": avg_processing_time,
            "tpu_stats": tpu_stats,
        }

    async def update_model(self, new_model_path: str) -> bool:
        """Update the detection model"""
        try:
            self.logger.info(f"Updating detection model to: {new_model_path}")

            # Try TPU first
            if self.tpu_manager:
                success = await self.tpu_manager.load_new_model(new_model_path)
                if success:
                    self._current_model_path = new_model_path
                    return True

            # Fall back to CPU
            if self.cpu_manager:
                success = await self.cpu_manager.initialize(new_model_path)
                if success:
                    self._current_model_path = new_model_path
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Error updating model: {e}")
            return False
