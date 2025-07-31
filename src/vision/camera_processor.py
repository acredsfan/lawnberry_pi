"""Camera frame processing and preprocessing module"""

import asyncio
import logging
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from pathlib import Path

from ..hardware.managers import CameraManager
from ..hardware.data_structures import CameraFrame
from .data_structures import VisionFrame, ProcessingMode


class CameraProcessor:
    """Handles camera frame processing and preprocessing"""
    
    def __init__(self, camera_manager: CameraManager):
        self.logger = logging.getLogger(__name__)
        self.camera_manager = camera_manager
        self._processing_lock = asyncio.Lock()
        
        # Processing statistics
        self.frames_processed = 0
        self.processing_times = []
        
    async def get_processed_frame(self, mode: ProcessingMode = ProcessingMode.REAL_TIME) -> Optional[VisionFrame]:
        """Get and preprocess the latest camera frame"""
        async with self._processing_lock:
            start_time = datetime.now()
            
            try:
                # Get latest frame from camera manager
                camera_frame = await self.camera_manager.get_latest_frame()
                if not camera_frame:
                    return None
                
                # Convert frame data to OpenCV format
                frame_array = np.frombuffer(camera_frame.data, dtype=np.uint8)
                cv_frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                
                if cv_frame is None:
                    self.logger.error("Failed to decode camera frame")
                    return None
                
                # Apply preprocessing based on mode
                processed_frame = await self._preprocess_frame(cv_frame, mode)
                
                # Calculate processing time
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                self.processing_times.append(processing_time)
                if len(self.processing_times) > 100:
                    self.processing_times.pop(0)
                
                # Create vision frame
                vision_frame = VisionFrame(
                    timestamp=camera_frame.timestamp,
                    frame_id=camera_frame.frame_id,
                    width=camera_frame.width,
                    height=camera_frame.height,
                    processing_time_ms=processing_time,
                    metadata={
                        'original_format': camera_frame.format,
                        'preprocessing_mode': mode.value,
                        'frame_size_bytes': len(camera_frame.data)
                    }
                )
                
                # Store processed frame data in metadata for further processing
                vision_frame.metadata['processed_frame'] = processed_frame
                
                self.frames_processed += 1
                return vision_frame
                
            except Exception as e:
                self.logger.error(f"Error processing camera frame: {e}")
                return None
    
    async def _preprocess_frame(self, frame: np.ndarray, mode: ProcessingMode) -> np.ndarray:
        """Apply preprocessing to camera frame"""
        try:
            processed = frame.copy()
            
            # Noise reduction
            if mode != ProcessingMode.TRAINING:  # Skip denoising for training to preserve original data
                processed = cv2.bilateralFilter(processed, 9, 75, 75)
            
            # Color correction and enhancement
            processed = self._enhance_colors(processed)
            
            # Image stabilization (basic implementation)
            if mode == ProcessingMode.REAL_TIME:
                processed = self._stabilize_image(processed)
            
            # Lighting adjustment
            processed = self._adjust_lighting(processed)
            
            return processed
            
        except Exception as e:
            self.logger.error(f"Error in frame preprocessing: {e}")
            return frame
    
    def _enhance_colors(self, frame: np.ndarray) -> np.ndarray:
        """Enhance color accuracy and saturation"""
        try:
            # Convert to LAB color space for better color processing
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            
            # Apply CLAHE to L channel for better contrast
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            
            # Merge channels and convert back
            enhanced = cv2.merge([l, a, b])
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
            
            return enhanced
            
        except Exception as e:
            self.logger.error(f"Error in color enhancement: {e}")
            return frame
    
    def _stabilize_image(self, frame: np.ndarray) -> np.ndarray:
        """Basic image stabilization using optical flow"""
        try:
            # Simple stabilization - can be enhanced with more sophisticated methods
            if not hasattr(self, '_prev_gray'):
                self._prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                return frame
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate optical flow for stabilization
            flow = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, gray, None, None,
                winSize=(15, 15), maxLevel=2
            )
            
            self._prev_gray = gray
            return frame  # Return original for now - can implement actual stabilization
            
        except Exception as e:
            self.logger.error(f"Error in image stabilization: {e}")
            return frame
    
    def _adjust_lighting(self, frame: np.ndarray) -> np.ndarray:
        """Adjust lighting conditions for better detection"""
        try:
            # Convert to HSV for lighting adjustments
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            h, s, v = cv2.split(hsv)
            
            # Calculate average brightness
            avg_brightness = np.mean(v)
            
            # Adjust brightness if too dark or too bright
            if avg_brightness < 80:  # Too dark
                v = cv2.add(v, int(80 - avg_brightness))
            elif avg_brightness > 200:  # Too bright
                v = cv2.subtract(v, int(avg_brightness - 200))
            
            # Merge and convert back
            adjusted = cv2.merge([h, s, v])
            adjusted = cv2.cvtColor(adjusted, cv2.COLOR_HSV2BGR)
            
            return adjusted
            
        except Exception as e:
            self.logger.error(f"Error in lighting adjustment: {e}")
            return frame
    
    async def save_frame_for_training(self, vision_frame: VisionFrame, save_path: Path) -> bool:
        """Save a frame for training purposes"""
        try:
            # Get the processed frame from metadata
            processed_frame = vision_frame.metadata.get('processed_frame')
            if processed_frame is None:
                self.logger.error("No processed frame data available")
                return False
            
            # Create save directory if it doesn't exist
            save_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save the frame
            success = cv2.imwrite(str(save_path), processed_frame)
            
            if success:
                self.logger.info(f"Training frame saved: {save_path}")
            else:
                self.logger.error(f"Failed to save training frame: {save_path}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error saving training frame: {e}")
            return False
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get frame processing statistics"""
        avg_processing_time = 0.0
        if self.processing_times:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times)
        
        return {
            'frames_processed': self.frames_processed,
            'average_processing_time_ms': avg_processing_time,
            'recent_processing_times': self.processing_times[-10:] if self.processing_times else []
        }
    
    async def detect_lighting_conditions(self, frame: np.ndarray) -> Dict[str, Any]:
        """Detect current lighting conditions"""
        try:
            # Convert to grayscale for analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate brightness statistics
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            # Detect shadows using edge detection
            edges = cv2.Canny(gray, 50, 150)
            shadow_ratio = np.sum(edges > 0) / edges.size
            
            # Classify lighting conditions
            if mean_brightness < 50:
                condition = "very_dark"
            elif mean_brightness < 100:
                condition = "dark"
            elif mean_brightness < 150:
                condition = "normal"
            elif mean_brightness < 200:
                condition = "bright"
            else:
                condition = "very_bright"
            
            return {
                'condition': condition,
                'mean_brightness': float(mean_brightness),
                'brightness_std': float(std_brightness),
                'shadow_ratio': float(shadow_ratio),
                'is_suitable_for_detection': 50 <= mean_brightness <= 200
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting lighting conditions: {e}")
            return {
                'condition': 'unknown',
                'mean_brightness': 0.0,
                'brightness_std': 0.0,
                'shadow_ratio': 0.0,
                'is_suitable_for_detection': False
            }
    
    async def detect_weather_conditions(self, frame: np.ndarray) -> Dict[str, Any]:
        """Detect weather conditions from camera frame"""
        try:
            # Simple rain detection using texture analysis
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate local standard deviation (texture measure)
            kernel = np.ones((5, 5), np.float32) / 25
            local_mean = cv2.filter2D(gray.astype(np.float32), -1, kernel)
            local_sqr_mean = cv2.filter2D((gray.astype(np.float32) ** 2), -1, kernel)
            local_variance = local_sqr_mean - (local_mean ** 2)
            texture_measure = np.mean(np.sqrt(local_variance))
            
            # Rain typically increases texture due to water droplets
            rain_detected = texture_measure > 15.0  # Threshold may need tuning
            
            # Fog detection using contrast measure
            contrast = gray.std()
            fog_detected = contrast < 20.0  # Low contrast indicates fog
            
            return {
                'rain_detected': rain_detected,
                'fog_detected': fog_detected,
                'texture_measure': float(texture_measure),
                'contrast_measure': float(contrast),
                'weather_suitable': not (rain_detected or fog_detected)
            }
            
        except Exception as e:
            self.logger.error(f"Error detecting weather conditions: {e}")
            return {
                'rain_detected': False,
                'fog_detected': False,
                'texture_measure': 0.0,
                'contrast_measure': 0.0,
                'weather_suitable': True
            }
