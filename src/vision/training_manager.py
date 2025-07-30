"""Training and continuous learning management for computer vision system"""

import asyncio
import logging
import json
import shutil
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import cv2

from .data_structures import (
    TrainingImage, VisionFrame, ObjectType, VisionConfig,
    DetectedObject, BoundingBox, ModelInfo
)


class TrainingManager:
    """Manages continuous learning and model adaptation"""
    
    def __init__(self, config: VisionConfig, data_storage_path: Path):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.data_storage_path = data_storage_path
        
        # Training data organization
        self.training_images_path = data_storage_path / "training_images"
        self.labeled_data_path = data_storage_path / "labeled_data"
        self.models_path = data_storage_path / "models"
        
        # Create directories
        self._create_directories()
        
        # Training state
        self._training_queue = []
        self._labeling_queue = []
        self._model_performance_history = []
        
        # Resource monitoring
        self._memory_usage = 0
        self._training_active = False
        
    def _create_directories(self):
        """Create necessary directories for training data"""
        directories = [
            self.training_images_path,
            self.labeled_data_path,
            self.models_path,
            self.training_images_path / "unlabeled",
            self.training_images_path / "labeled",
            self.training_images_path / "validated"
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    async def collect_training_image(self, vision_frame: VisionFrame, 
                                   trigger_reason: str = "manual") -> bool:
        """Collect a frame for training purposes"""
        try:
            if not self.config.enable_continuous_learning:
                return False
            
            # Check resource constraints
            if not await self._check_resource_constraints():
                self.logger.warning("Resource constraints prevent training data collection")
                return False
            
            # Generate unique filename
            timestamp = vision_frame.timestamp.strftime("%Y%m%d_%H%M%S_%f")
            filename = f"frame_{timestamp}_{trigger_reason}.jpg"
            image_path = self.training_images_path / "unlabeled" / filename
            
            # Get the processed frame from metadata
            frame_data = vision_frame.metadata.get('processed_frame')
            if frame_data is None:
                self.logger.error("No frame data available for training collection")
                return False
            
            # Save the image
            success = cv2.imwrite(str(image_path), frame_data)
            if not success:
                self.logger.error(f"Failed to save training image: {image_path}")
                return False
            
            # Create training image record
            training_image = TrainingImage(
                timestamp=vision_frame.timestamp,
                image_path=str(image_path),
                width=vision_frame.width,
                height=vision_frame.height,
                metadata={
                    'trigger_reason': trigger_reason,
                    'processing_time_ms': vision_frame.processing_time_ms,
                    'model_version': vision_frame.model_version,
                    'tpu_used': vision_frame.tpu_used,
                    'detected_objects_count': len(vision_frame.objects),
                    'lighting_conditions': await self._analyze_lighting(frame_data),
                    'collection_method': 'automatic' if trigger_reason != 'manual' else 'manual'
                }
            )
            
            # Add to labeling queue if it contains interesting objects
            if self._should_prioritize_for_labeling(vision_frame):
                self._labeling_queue.append(training_image)
            
            # Save metadata
            await self._save_training_metadata(training_image)
            
            self.logger.info(f"Training image collected: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error collecting training image: {e}")
            return False
    
    async def label_training_image(self, image_path: str, 
                                 labels: List[Dict[str, Any]]) -> bool:
        """Add labels to a training image"""
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                self.logger.error(f"Training image not found: {image_path}")
                return False
            
            # Load existing metadata
            metadata_path = image_path.with_suffix('.json')
            training_image = None
            
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    training_image = TrainingImage(**metadata)
            
            if not training_image:
                self.logger.error(f"No metadata found for training image: {image_path}")
                return False
            
            # Validate and process labels
            processed_labels = await self._process_labels(labels, training_image)
            training_image.labels = processed_labels
            training_image.is_labeled = True
            
            # Move to labeled directory
            labeled_path = self.training_images_path / "labeled" / image_path.name
            shutil.move(str(image_path), str(labeled_path))
            training_image.image_path = str(labeled_path)
            
            # Save updated metadata
            await self._save_training_metadata(training_image)
            
            # Remove from labeling queue
            self._labeling_queue = [img for img in self._labeling_queue 
                                  if img.image_path != str(image_path)]
            
            self.logger.info(f"Training image labeled: {labeled_path.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error labeling training image: {e}")
            return False
    
    async def trigger_model_retraining(self) -> bool:
        """Trigger retraining of the detection model"""
        if not self.config.enable_continuous_learning:
            return False
        
        if self._training_active:
            self.logger.warning("Training already in progress")
            return False
        
        try:
            # Check if we have enough labeled data
            labeled_count = await self._count_labeled_images()
            if labeled_count < self.config.min_training_samples:
                self.logger.info(f"Not enough labeled samples for training: {labeled_count}/{self.config.min_training_samples}")
                return False
            
            # Check resource constraints
            if not await self._check_resource_constraints():
                self.logger.warning("Resource constraints prevent model retraining")
                return False
            
            self._training_active = True
            self.logger.info("Starting model retraining...")
            
            # Prepare training data
            training_data = await self._prepare_training_data()
            if not training_data:
                self.logger.error("Failed to prepare training data")
                self._training_active = False
                return False
            
            # Run training (simplified - in practice would use proper ML training pipeline)
            success = await self._run_training(training_data)
            
            self._training_active = False
            
            if success:
                self.logger.info("Model retraining completed successfully")
                return True
            else:
                self.logger.error("Model retraining failed")
                return False
            
        except Exception as e:
            self.logger.error(f"Error during model retraining: {e}")
            self._training_active = False
            return False
    
    async def _process_labels(self, labels: List[Dict[str, Any]], 
                            training_image: TrainingImage) -> List[Dict[str, Any]]:
        """Process and validate label data"""
        processed_labels = []
        
        for label in labels:
            try:
                # Validate required fields
                if 'object_type' not in label or 'bbox' not in label:
                    self.logger.warning(f"Invalid label format: {label}")
                    continue
                
                # Normalize bounding box coordinates
                bbox = label['bbox']
                normalized_bbox = {
                    'x': max(0, min(bbox['x'] / training_image.width, 1.0)),
                    'y': max(0, min(bbox['y'] / training_image.height, 1.0)),
                    'width': max(0, min(bbox['width'] / training_image.width, 1.0)),
                    'height': max(0, min(bbox['height'] / training_image.height, 1.0))
                }
                
                processed_label = {
                    'object_type': label['object_type'],
                    'bbox': normalized_bbox,
                    'confidence': label.get('confidence', 1.0),
                    'difficulty': label.get('difficulty', 'normal'),
                    'verified': label.get('verified', False),
                    'labeler': label.get('labeler', 'auto'),
                    'timestamp': datetime.now().isoformat()
                }
                
                processed_labels.append(processed_label)
                
            except Exception as e:
                self.logger.error(f"Error processing label: {e}")
                continue
        
        return processed_labels
    
    async def _prepare_training_data(self) -> Optional[Dict[str, Any]]:
        """Prepare training data for model retraining"""
        try:
            labeled_images = []
            labeled_dir = self.training_images_path / "labeled"
            
            # Collect all labeled images
            for image_path in labeled_dir.glob("*.jpg"):
                metadata_path = image_path.with_suffix('.json')
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        training_image = TrainingImage(**metadata)
                        labeled_images.append(training_image)
            
            if not labeled_images:
                return None
            
            # Split into train/validation sets
            train_split = 0.8
            split_index = int(len(labeled_images) * train_split)
            
            train_images = labeled_images[:split_index]
            val_images = labeled_images[split_index:]
            
            return {
                'train_images': train_images,
                'val_images': val_images,
                'total_samples': len(labeled_images),
                'num_classes': len(set(label['object_type'] 
                                     for img in labeled_images 
                                     for label in img.labels))
            }
            
        except Exception as e:
            self.logger.error(f"Error preparing training data: {e}")
            return None
    
    async def _run_training(self, training_data: Dict[str, Any]) -> bool:
        """Run the actual model training (placeholder implementation)"""
        try:
            # This is a simplified placeholder implementation
            # In practice, this would involve:
            # 1. Converting data to appropriate format (TFRecord, etc.)
            # 2. Setting up training pipeline with TensorFlow/PyTorch
            # 3. Running training with appropriate hyperparameters
            # 4. Validating the model
            # 5. Converting to TensorFlow Lite and optimizing for TPU
            
            self.logger.info("Training simulation started...")
            
            # Simulate training time
            for epoch in range(5):
                await asyncio.sleep(1)  # Simulate training time
                self.logger.info(f"Training epoch {epoch + 1}/5 completed")
            
            # Create a new model info record
            model_info = ModelInfo(
                name="retrained_efficientdet",
                version=f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                path=str(self.models_path / "latest_retrained.tflite"),
                accuracy=0.92,  # Simulated accuracy
                inference_time_ms=45.0,
                tpu_optimized=True,
                created_at=datetime.now(),
                metadata={
                    'training_samples': training_data['total_samples'],
                    'num_classes': training_data['num_classes'],
                    'training_method': 'transfer_learning'
                }
            )
            
            # Save model info
            self._model_performance_history.append(model_info)
            
            self.logger.info("Training simulation completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during training: {e}")
            return False
    
    async def get_training_statistics(self) -> Dict[str, Any]:
        """Get training and learning statistics"""
        try:
            # Count images in different stages
            unlabeled_count = len(list((self.training_images_path / "unlabeled").glob("*.jpg")))
            labeled_count = len(list((self.training_images_path / "labeled").glob("*.jpg")))
            validated_count = len(list((self.training_images_path / "validated").glob("*.jpg")))
            
            # Calculate labeling progress
            total_collected = unlabeled_count + labeled_count + validated_count
            labeling_progress = labeled_count / max(total_collected, 1)
            
            # Get recent model performance
            recent_models = self._model_performance_history[-5:] if self._model_performance_history else []
            
            return {
                'continuous_learning_enabled': self.config.enable_continuous_learning,
                'training_active': self._training_active,
                'images_collected': {
                    'unlabeled': unlabeled_count,
                    'labeled': labeled_count,
                    'validated': validated_count,
                    'total': total_collected
                },
                'labeling_progress': labeling_progress,
                'labeling_queue_size': len(self._labeling_queue),
                'training_queue_size': len(self._training_queue),
                'min_samples_for_training': self.config.min_training_samples,
                'recent_models': [model.__dict__ for model in recent_models],
                'storage_usage_mb': await self._calculate_storage_usage()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting training statistics: {e}")
            return {}
    
    async def cleanup_old_training_data(self):
        """Clean up old training data based on retention policy"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config.training_data_retention_days)
            
            # Clean up old unlabeled images
            unlabeled_dir = self.training_images_path / "unlabeled"
            cleaned_count = 0
            
            for image_path in unlabeled_dir.glob("*.jpg"):
                if image_path.stat().st_mtime < cutoff_date.timestamp():
                    # Remove image and metadata
                    image_path.unlink()
                    metadata_path = image_path.with_suffix('.json')
                    if metadata_path.exists():
                        metadata_path.unlink()
                    cleaned_count += 1
            
            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} old training images")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up training data: {e}")
    
    async def export_training_dataset(self, export_path: Path, 
                                    format: str = "coco") -> bool:
        """Export training dataset in specified format"""
        try:
            export_path.mkdir(parents=True, exist_ok=True)
            
            if format.lower() == "coco":
                return await self._export_coco_format(export_path)
            elif format.lower() == "yolo":
                return await self._export_yolo_format(export_path)
            else:
                self.logger.error(f"Unsupported export format: {format}")
                return False
            
        except Exception as e:
            self.logger.error(f"Error exporting training dataset: {e}")
            return False
    
    async def _export_coco_format(self, export_path: Path) -> bool:
        """Export dataset in COCO format"""
        try:
            # Create COCO annotation structure
            coco_data = {
                "images": [],
                "annotations": [],
                "categories": []
            }
            
            # Add categories
            object_types = list(ObjectType)
            for i, obj_type in enumerate(object_types):
                coco_data["categories"].append({
                    "id": i,
                    "name": obj_type.value,
                    "supercategory": "lawn_object"
                })
            
            # Process labeled images
            labeled_dir = self.training_images_path / "labeled"
            annotation_id = 1
            
            for image_id, image_path in enumerate(labeled_dir.glob("*.jpg"), 1):
                metadata_path = image_path.with_suffix('.json')
                if not metadata_path.exists():
                    continue
                
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    training_image = TrainingImage(**metadata)
                
                # Add image info
                coco_data["images"].append({
                    "id": image_id,
                    "file_name": image_path.name,
                    "width": training_image.width,
                    "height": training_image.height
                })
                
                # Add annotations
                for label in training_image.labels:
                    bbox = label['bbox']
                    # Convert to COCO format (x, y, width, height)
                    coco_bbox = [
                        bbox['x'] * training_image.width,
                        bbox['y'] * training_image.height,
                        bbox['width'] * training_image.width,
                        bbox['height'] * training_image.height
                    ]
                    
                    coco_data["annotations"].append({
                        "id": annotation_id,
                        "image_id": image_id,
                        "category_id": self._get_category_id(label['object_type']),
                        "bbox": coco_bbox,
                        "area": coco_bbox[2] * coco_bbox[3],
                        "iscrowd": 0
                    })
                    annotation_id += 1
            
            # Save COCO annotations
            annotations_path = export_path / "annotations.json"
            with open(annotations_path, 'w') as f:
                json.dump(coco_data, f, indent=2)
            
            # Copy images
            images_dir = export_path / "images"
            images_dir.mkdir(exist_ok=True)
            
            for image_path in labeled_dir.glob("*.jpg"):
                shutil.copy2(image_path, images_dir / image_path.name)
            
            self.logger.info(f"Dataset exported in COCO format to: {export_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting COCO dataset: {e}")
            return False
    
    async def _export_yolo_format(self, export_path: Path) -> bool:
        """Export dataset in YOLO format"""
        # Similar implementation for YOLO format
        # This is a placeholder - implement based on YOLO requirements
        self.logger.info("YOLO export not yet implemented")
        return False
    
    def _get_category_id(self, object_type_str: str) -> int:
        """Get category ID for object type string"""
        object_types = list(ObjectType)
        for i, obj_type in enumerate(object_types):
            if obj_type.value == object_type_str:
                return i
        return 0  # Default to first category
    
    def _should_prioritize_for_labeling(self, vision_frame: VisionFrame) -> bool:
        """Determine if frame should be prioritized for labeling"""
        # Prioritize frames with detected objects or interesting conditions
        if len(vision_frame.objects) > 0:
            return True
        
        # Prioritize frames with poor detection confidence
        if vision_frame.processing_time_ms > self.config.max_processing_time_ms:
            return True
        
        return False
    
    async def _check_resource_constraints(self) -> bool:
        """Check if resource constraints allow training operations"""
        try:
            # Check available disk space
            storage_usage = await self._calculate_storage_usage()
            if storage_usage > self.config.max_memory_usage_mb:
                return False
            
            # Check if training is already active
            if self._training_active:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking resource constraints: {e}")
            return False
    
    async def _calculate_storage_usage(self) -> float:
        """Calculate storage usage in MB"""
        try:
            total_size = 0
            for path in [self.training_images_path, self.labeled_data_path, self.models_path]:
                if path.exists():
                    for file_path in path.rglob("*"):
                        if file_path.is_file():
                            total_size += file_path.stat().st_size
            
            return total_size / (1024 * 1024)  # Convert to MB
            
        except Exception as e:
            self.logger.error(f"Error calculating storage usage: {e}")
            return 0.0
    
    async def _save_training_metadata(self, training_image: TrainingImage):
        """Save training image metadata to JSON file"""
        try:
            image_path = Path(training_image.image_path)
            metadata_path = image_path.with_suffix('.json')
            
            # Convert to serializable format
            metadata = {
                'timestamp': training_image.timestamp.isoformat(),
                'image_path': training_image.image_path,
                'width': training_image.width,
                'height': training_image.height,
                'labels': training_image.labels,
                'metadata': training_image.metadata,
                'is_labeled': training_image.is_labeled
            }
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving training metadata: {e}")
    
    async def _analyze_lighting(self, frame: np.ndarray) -> Dict[str, Any]:
        """Analyze lighting conditions of a frame"""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_brightness = np.mean(gray)
            std_brightness = np.std(gray)
            
            return {
                'mean_brightness': float(mean_brightness),
                'brightness_std': float(std_brightness),
                'condition': 'normal' if 50 <= mean_brightness <= 200 else 'challenging'
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing lighting: {e}")
            return {'condition': 'unknown'}
    
    async def _count_labeled_images(self) -> int:
        """Count the number of labeled training images"""
        try:
            labeled_dir = self.training_images_path / "labeled"
            return len(list(labeled_dir.glob("*.jpg")))
        except Exception as e:
            self.logger.error(f"Error counting labeled images: {e}")
            return 0
