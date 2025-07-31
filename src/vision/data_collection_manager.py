"""
Automated data collection and annotation system for continuous model improvement.
Implements privacy-preserving data collection with intelligent sampling.
"""

import asyncio
import logging
import json
import hashlib
import time
import cv2
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from collections import deque
import threading
import queue

from .data_structures import VisionFrame, DetectedObject


class DataCollectionManager:
    """Manages automated data collection and annotation for model improvement"""
    
    def __init__(self, storage_path: Path, config: Dict[str, Any]):
        self.logger = logging.getLogger(__name__)
        self.storage_path = storage_path
        self.config = config
        
        # Create storage directories
        self.storage_dirs = {
            'raw_images': storage_path / 'raw_images',
            'annotated_images': storage_path / 'annotated_images',
            'obstacle_samples': storage_path / 'obstacle_samples',
            'grass_samples': storage_path / 'grass_samples',
            'weather_samples': storage_path / 'weather_samples',
            'terrain_samples': storage_path / 'terrain_samples',
            'edge_cases': storage_path / 'edge_cases',
            'validation_data': storage_path / 'validation_data'
        }
        
        for dir_path in self.storage_dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Data collection state
        self._collection_active = False
        self._collection_stats = {
            'total_samples': 0,
            'obstacle_samples': 0,
            'grass_samples': 0,
            'weather_samples': 0,
            'terrain_samples': 0,
            'edge_case_samples': 0,
            'last_collection': None
        }
        
        # Intelligent sampling
        self._sample_buffer = deque(maxlen=1000)
        self._recent_hashes = set()
        self._hash_cleanup_counter = 0
        
        # Quality validation
        self._quality_thresholds = {
            'min_brightness': 30,
            'max_brightness': 250,
            'min_contrast': 20,
            'blur_threshold': 100,
            'min_size': (160, 120)
        }
        
        # Privacy protection
        self._privacy_zones = []  # Areas to blur/exclude
        self._anonymization_enabled = config.get('anonymization_enabled', True)
        
        # Background processing
        self._processing_queue = queue.Queue(maxsize=100)
        self._processing_thread = None
        
    async def initialize(self) -> bool:
        """Initialize data collection system"""
        try:
            self.logger.info("Initializing automated data collection system...")
            
            # Load existing statistics
            await self._load_collection_stats()
            
            # Start background processing
            self._start_background_processing()
            
            self.logger.info("Data collection system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize data collection: {e}")
            return False
    
    def _start_background_processing(self):
        """Start background thread for data processing"""
        if self._processing_thread and self._processing_thread.is_alive():
            return
        
        self._processing_thread = threading.Thread(
            target=self._background_processing_loop,
            daemon=True
        )
        self._processing_thread.start()
    
    def _background_processing_loop(self):
        """Background processing loop for data annotation and organization"""
        while True:
            try:
                # Get next item to process
                item = self._processing_queue.get(timeout=1.0)
                if item is None:  # Shutdown signal
                    break
                
                self._process_collected_sample(item)
                self._processing_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in background processing: {e}")
    
    async def collect_sample(self, vision_frame: VisionFrame, detections: List[DetectedObject], 
                           metadata: Dict[str, Any]) -> bool:
        """Collect a sample with intelligent filtering"""
        try:
            if not self._collection_active:
                return False
            
            # Quality validation
            if not self._validate_sample_quality(vision_frame):
                return False
            
            # Intelligent sampling - avoid duplicates
            sample_hash = self._calculate_sample_hash(vision_frame)
            if sample_hash in self._recent_hashes:
                return False  # Skip similar samples
            
            # Determine sample type and importance
            sample_info = self._analyze_sample_importance(vision_frame, detections, metadata)
            
            # Apply collection strategy
            if not self._should_collect_sample(sample_info):
                return False
            
            # Privacy protection
            processed_frame = await self._apply_privacy_protection(vision_frame)
            
            # Add to processing queue
            collection_item = {
                'frame': processed_frame,
                'detections': detections,
                'metadata': metadata,
                'sample_info': sample_info,
                'timestamp': time.time(),
                'hash': sample_hash
            }
            
            try:
                self._processing_queue.put_nowait(collection_item)
                self._recent_hashes.add(sample_hash)
                
                # Cleanup old hashes periodically
                self._hash_cleanup_counter += 1
                if self._hash_cleanup_counter >= 100:
                    await self._cleanup_recent_hashes()
                    self._hash_cleanup_counter = 0
                
                return True
                
            except queue.Full:
                self.logger.warning("Data collection queue full, skipping sample")
                return False
            
        except Exception as e:
            self.logger.error(f"Error collecting sample: {e}")
            return False
    
    def _validate_sample_quality(self, vision_frame: VisionFrame) -> bool:
        """Validate sample meets quality requirements"""
        try:
            frame = vision_frame.raw_frame
            if frame is None:
                return False
            
            # Check dimensions
            h, w = frame.shape[:2]
            min_w, min_h = self._quality_thresholds['min_size']
            if w < min_w or h < min_h:
                return False
            
            # Check brightness
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            brightness = np.mean(gray)
            if brightness < self._quality_thresholds['min_brightness'] or brightness > self._quality_thresholds['max_brightness']:
                return False
            
            # Check contrast
            contrast = np.std(gray)
            if contrast < self._quality_thresholds['min_contrast']:
                return False
            
            # Check blur (Laplacian variance)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            if blur_score < self._quality_thresholds['blur_threshold']:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating sample quality: {e}")
            return False
    
    def _calculate_sample_hash(self, vision_frame: VisionFrame) -> str:
        """Calculate hash for duplicate detection"""
        try:
            frame = vision_frame.raw_frame
            if frame is None:
                return ""
            
            # Resize to small size for hash calculation
            small_frame = cv2.resize(frame, (64, 64))
            frame_bytes = small_frame.tobytes()
            
            return hashlib.md5(frame_bytes).hexdigest()
            
        except Exception as e:
            self.logger.error(f"Error calculating sample hash: {e}")
            return ""
    
    def _analyze_sample_importance(self, vision_frame: VisionFrame, detections: List[DetectedObject], 
                                 metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze sample to determine collection importance"""
        importance_score = 0.0
        sample_types = []
        reasons = []
        
        # Check for obstacles
        if detections:
            importance_score += len(detections) * 0.3
            sample_types.append('obstacle_detection')
            reasons.append(f"Contains {len(detections)} detected objects")
            
            # Higher importance for rare object types
            rare_objects = ['person', 'pet', 'sprinkler_head', 'electrical_cable']
            for detection in detections:
                if hasattr(detection, 'object_type') and detection.object_type in rare_objects:
                    importance_score += 0.5
                    reasons.append(f"Contains rare object: {detection.object_type}")
        
        # Check grass conditions
        frame = vision_frame.raw_frame
        if frame is not None:
            # Analyze grass health indicators
            green_ratio = self._calculate_green_ratio(frame)
            if green_ratio < 0.3 or green_ratio > 0.8:  # Unusual grass conditions
                importance_score += 0.4
                sample_types.append('grass_analysis')
                reasons.append(f"Unusual grass conditions (green ratio: {green_ratio:.2f})")
        
        # Check weather conditions
        weather_score = self._analyze_weather_conditions(frame, metadata)
        if weather_score > 0.5:
            importance_score += weather_score
            sample_types.append('weather_analysis')
            reasons.append("Interesting weather conditions")
        
        # Check terrain features
        terrain_score = self._analyze_terrain_features(frame)
        if terrain_score > 0.5:
            importance_score += terrain_score
            sample_types.append('terrain_analysis')
            reasons.append("Complex terrain features")
        
        # Edge cases (high importance)
        if importance_score > 1.5:
            sample_types.append('edge_case')
            importance_score += 0.5
            reasons.append("Classified as edge case")
        
        return {
            'importance_score': importance_score,
            'sample_types': sample_types,
            'reasons': reasons,
            'collection_priority': min(importance_score, 2.0)
        }
    
    def _calculate_green_ratio(self, frame: np.ndarray) -> float:
        """Calculate ratio of green pixels in frame"""
        try:
            if len(frame.shape) != 3:
                return 0.0
            
            # Convert to HSV for better green detection
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            # Define green range in HSV
            lower_green = np.array([35, 50, 50])
            upper_green = np.array([85, 255, 255])
            
            # Create mask for green pixels
            green_mask = cv2.inRange(hsv, lower_green, upper_green)
            
            # Calculate ratio
            green_pixels = np.sum(green_mask > 0)
            total_pixels = frame.shape[0] * frame.shape[1]
            
            return green_pixels / total_pixels if total_pixels > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"Error calculating green ratio: {e}")
            return 0.0
    
    def _analyze_weather_conditions(self, frame: np.ndarray, metadata: Dict[str, Any]) -> float:
        """Analyze weather conditions for collection importance"""
        score = 0.0
        
        try:
            if frame is None:
                return 0.0
            
            # Brightness analysis for weather
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            brightness = np.mean(gray)
            
            # Very bright or very dark conditions
            if brightness < 50 or brightness > 200:
                score += 0.3
            
            # High contrast variation (storm/mixed conditions)
            contrast = np.std(gray)
            if contrast > 60:
                score += 0.4
            
            # Check metadata for weather info
            if 'weather' in metadata:
                weather_type = metadata['weather'].get('condition', '')
                rare_conditions = ['rain', 'snow', 'fog', 'storm']
                if any(condition in weather_type.lower() for condition in rare_conditions):
                    score += 0.6
            
            return min(score, 1.0)
            
        except Exception as e:
            self.logger.error(f"Error analyzing weather conditions: {e}")
            return 0.0
    
    def _analyze_terrain_features(self, frame: np.ndarray) -> float:
        """Analyze terrain complexity for collection importance"""
        score = 0.0
        
        try:
            if frame is None:
                return 0.0
            
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            
            # Edge detection for terrain complexity
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
            
            if edge_density > 0.1:  # High edge density indicates complex terrain
                score += 0.5
            
            # Texture analysis using standard deviation in local patches
            h, w = gray.shape
            patch_size = 32
            texture_scores = []
            
            for y in range(0, h - patch_size, patch_size):
                for x in range(0, w - patch_size, patch_size):
                    patch = gray[y:y+patch_size, x:x+patch_size]
                    texture_scores.append(np.std(patch))
            
            if texture_scores:
                avg_texture = np.mean(texture_scores)
                if avg_texture > 30:  # High texture variation
                    score += 0.4
            
            return min(score, 1.0)
            
        except Exception as e:
            self.logger.error(f"Error analyzing terrain features: {e}")
            return 0.0
    
    def _should_collect_sample(self, sample_info: Dict[str, Any]) -> bool:
        """Decide whether to collect sample based on strategy"""
        importance_score = sample_info['importance_score']
        
        # Always collect high-importance samples
        if importance_score >= 1.5:
            return True
        
        # Collect medium-importance samples with probability
        if importance_score >= 0.8:
            return np.random.random() < 0.7
        
        # Collect low-importance samples occasionally for baseline
        if importance_score >= 0.3:
            return np.random.random() < 0.2
        
        # Very low importance - collect rarely
        return np.random.random() < 0.05
    
    async def _apply_privacy_protection(self, vision_frame: VisionFrame) -> VisionFrame:
        """Apply privacy protection to collected samples"""
        if not self._anonymization_enabled:
            return vision_frame
        
        try:
            frame = vision_frame.raw_frame.copy()
            
            # Blur privacy zones if defined
            for zone in self._privacy_zones:
                x, y, w, h = zone
                if x + w <= frame.shape[1] and y + h <= frame.shape[0]:
                    roi = frame[y:y+h, x:x+w]
                    blurred_roi = cv2.GaussianBlur(roi, (23, 23), 0)
                    frame[y:y+h, x:x+w] = blurred_roi
            
            # Create anonymized vision frame
            anonymized_frame = VisionFrame(
                raw_frame=frame,
                processed_frame=vision_frame.processed_frame,
                timestamp=vision_frame.timestamp,
                frame_id=vision_frame.frame_id,
                metadata=vision_frame.metadata.copy()
            )
            
            # Mark as anonymized
            anonymized_frame.metadata['anonymized'] = True
            
            return anonymized_frame
            
        except Exception as e:
            self.logger.error(f"Error applying privacy protection: {e}")
            return vision_frame
    
    def _process_collected_sample(self, collection_item: Dict[str, Any]):
        """Process and store collected sample"""
        try:
            frame = collection_item['frame']
            detections = collection_item['detections']
            sample_info = collection_item['sample_info']
            timestamp = collection_item['timestamp']
            
            # Generate filename
            dt = datetime.fromtimestamp(timestamp)
            base_filename = f"{dt.strftime('%Y%m%d_%H%M%S')}_{collection_item['hash'][:8]}"
            
            # Save to appropriate directories based on sample types
            for sample_type in sample_info['sample_types']:
                self._save_sample_by_type(frame, detections, sample_type, base_filename, sample_info)
            
            # Update statistics
            self._update_collection_stats(sample_info)
            
            self.logger.debug(f"Processed sample: {base_filename} (types: {sample_info['sample_types']})")
            
        except Exception as e:
            self.logger.error(f"Error processing collected sample: {e}")
    
    def _save_sample_by_type(self, frame: VisionFrame, detections: List[DetectedObject], 
                           sample_type: str, base_filename: str, sample_info: Dict[str, Any]):
        """Save sample to appropriate directory based on type"""
        try:
            # Determine storage directory
            if sample_type == 'obstacle_detection':
                storage_dir = self.storage_dirs['obstacle_samples']
            elif sample_type == 'grass_analysis':
                storage_dir = self.storage_dirs['grass_samples']
            elif sample_type == 'weather_analysis':
                storage_dir = self.storage_dirs['weather_samples']
            elif sample_type == 'terrain_analysis':
                storage_dir = self.storage_dirs['terrain_samples']
            elif sample_type == 'edge_case':
                storage_dir = self.storage_dirs['edge_cases']
            else:
                storage_dir = self.storage_dirs['raw_images']
            
            # Save image
            image_path = storage_dir / f"{base_filename}.jpg"
            cv2.imwrite(str(image_path), frame.raw_frame)
            
            # Save annotation data
            annotation_data = {
                'filename': f"{base_filename}.jpg",
                'timestamp': frame.timestamp,
                'sample_type': sample_type,
                'importance_score': sample_info['importance_score'],
                'reasons': sample_info['reasons'],
                'detections': [
                    {
                        'object_type': str(det.object_type) if hasattr(det, 'object_type') else 'unknown',
                        'bbox': det.bounding_box.__dict__ if hasattr(det, 'bounding_box') else {},
                        'confidence': det.confidence if hasattr(det, 'confidence') else 0.0
                    }
                    for det in detections
                ],
                'frame_metadata': frame.metadata
            }
            
            annotation_path = storage_dir / f"{base_filename}.json"
            with open(annotation_path, 'w') as f:
                json.dump(annotation_data, f, indent=2, default=str)
            
        except Exception as e:
            self.logger.error(f"Error saving sample {base_filename} as {sample_type}: {e}")
    
    def _update_collection_stats(self, sample_info: Dict[str, Any]):
        """Update collection statistics"""
        self._collection_stats['total_samples'] += 1
        self._collection_stats['last_collection'] = time.time()
        
        for sample_type in sample_info['sample_types']:
            if sample_type == 'obstacle_detection':
                self._collection_stats['obstacle_samples'] += 1
            elif sample_type == 'grass_analysis':
                self._collection_stats['grass_samples'] += 1
            elif sample_type == 'weather_analysis':
                self._collection_stats['weather_samples'] += 1
            elif sample_type == 'terrain_analysis':
                self._collection_stats['terrain_samples'] += 1
            elif sample_type == 'edge_case':
                self._collection_stats['edge_case_samples'] += 1
    
    async def _cleanup_recent_hashes(self):
        """Clean up old hashes to prevent memory buildup"""
        # Keep only recent hashes (last 1000)
        if len(self._recent_hashes) > 1000:
            # Convert to list, sort, and keep newest
            hash_list = list(self._recent_hashes)
            self._recent_hashes = set(hash_list[-1000:])
    
    async def _load_collection_stats(self):
        """Load existing collection statistics"""
        try:
            stats_path = self.storage_path / 'collection_stats.json'
            if stats_path.exists():
                with open(stats_path, 'r') as f:
                    saved_stats = json.load(f)
                    self._collection_stats.update(saved_stats)
                self.logger.info(f"Loaded collection stats: {self._collection_stats['total_samples']} total samples")
        except Exception as e:
            self.logger.error(f"Error loading collection stats: {e}")
    
    async def save_collection_stats(self):
        """Save collection statistics"""
        try:
            stats_path = self.storage_path / 'collection_stats.json'
            with open(stats_path, 'w') as f:
                json.dump(self._collection_stats, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Error saving collection stats: {e}")
    
    def start_collection(self):
        """Start data collection"""
        self._collection_active = True
        self.logger.info("Data collection started")
    
    def stop_collection(self):
        """Stop data collection"""
        self._collection_active = False
        self.logger.info("Data collection stopped")
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get current collection statistics"""
        stats = self._collection_stats.copy()
        stats['collection_active'] = self._collection_active
        stats['queue_size'] = self._processing_queue.qsize()
        return stats
    
    def add_privacy_zone(self, x: int, y: int, width: int, height: int):
        """Add privacy zone to blur in collected samples"""
        self._privacy_zones.append((x, y, width, height))
        self.logger.info(f"Added privacy zone: ({x}, {y}, {width}, {height})")
    
    def clear_privacy_zones(self):
        """Clear all privacy zones"""
        self._privacy_zones.clear()
        self.logger.info("Cleared all privacy zones")
    
    async def shutdown(self):
        """Shutdown data collection system"""
        try:
            self.stop_collection()
            
            # Save final statistics
            await self.save_collection_stats()
            
            # Stop background processing
            if self._processing_thread and self._processing_thread.is_alive():
                self._processing_queue.put(None)  # Shutdown signal
                self._processing_thread.join(timeout=5.0)
            
            self.logger.info("Data collection system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during data collection shutdown: {e}")
