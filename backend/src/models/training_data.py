"""
TrainingData model for LawnBerry Pi v2
AI training dataset management and image collection
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict
import uuid


class DatasetFormat(str, Enum):
    """Dataset export formats"""
    COCO = "coco"  # COCO JSON format
    YOLO = "yolo"  # YOLO text annotations
    PASCAL_VOC = "pascal_voc"  # Pascal VOC XML
    TENSORFLOW = "tensorflow"  # TensorFlow TFRecord
    CUSTOM = "custom"  # Custom JSON format


class LabelStatus(str, Enum):
    """Image labeling status"""
    UNLABELED = "unlabeled"
    PARTIAL = "partial"  # Some objects labeled
    COMPLETE = "complete"  # All objects labeled
    VERIFIED = "verified"  # Labels reviewed and verified
    REJECTED = "rejected"  # Image rejected for training


class AnnotationType(str, Enum):
    """Types of annotations"""
    BOUNDING_BOX = "bounding_box"
    POLYGON = "polygon"
    POINT = "point"
    CLASSIFICATION = "classification"
    SEGMENTATION = "segmentation"


class BoundingBoxAnnotation(BaseModel):
    """Bounding box annotation"""
    x: float  # Normalized coordinates (0.0-1.0)
    y: float
    width: float
    height: float
    
    @field_validator('x', 'y', 'width', 'height')
    def validate_normalized_coords(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Coordinates must be normalized between 0.0 and 1.0')
        return v


class ObjectAnnotation(BaseModel):
    """Single object annotation"""
    annotation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    class_name: str
    class_id: int
    confidence: float = 1.0  # Annotation confidence (for auto-annotations)
    
    # Annotation data based on type
    annotation_type: AnnotationType = AnnotationType.BOUNDING_BOX
    bounding_box: Optional[BoundingBoxAnnotation] = None
    polygon_points: Optional[List[List[float]]] = None  # [[x1,y1], [x2,y2], ...]
    center_point: Optional[List[float]] = None  # [x, y]
    
    # Metadata
    annotator: str = "system"  # "system", "user", "auto"
    annotation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verification_status: str = "unverified"  # "unverified", "verified", "rejected"
    
    @field_validator('confidence')
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v


class TrainingImage(BaseModel):
    """Training image with annotations"""
    image_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    original_path: str
    
    # Image properties
    width: int
    height: int
    format: str = "jpeg"  # jpeg, png, etc.
    file_size_bytes: int = 0
    checksum: Optional[str] = None
    
    # Capture metadata
    capture_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    camera_config: Dict[str, Any] = Field(default_factory=dict)
    environmental_conditions: Dict[str, Any] = Field(default_factory=dict)
    
    # Location and context
    gps_location: Optional[Dict[str, float]] = None  # {"lat": x, "lon": y}
    robot_state: Optional[Dict[str, Any]] = None  # Robot state when captured
    scene_context: Optional[str] = None  # Description of scene
    
    # Annotations
    annotations: List[ObjectAnnotation] = Field(default_factory=list)
    label_status: LabelStatus = LabelStatus.UNLABELED
    
    # Quality metrics
    quality_score: Optional[float] = None  # 0.0-1.0
    blur_score: Optional[float] = None
    exposure_score: Optional[float] = None
    
    # Training usage
    dataset_splits: List[str] = Field(default_factory=list)  # ["train", "val", "test"]
    exclude_from_training: bool = False
    exclusion_reason: Optional[str] = None
    
    # Processing history
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_history: List[Dict[str, Any]] = Field(default_factory=list)
    
    def add_annotation(self, annotation: ObjectAnnotation):
        """Add an object annotation"""
        self.annotations.append(annotation)
        self.last_modified = datetime.now(timezone.utc)
        
        # Update label status
        if self.label_status == LabelStatus.UNLABELED:
            self.label_status = LabelStatus.PARTIAL
    
    def get_class_counts(self) -> Dict[str, int]:
        """Get count of annotations by class"""
        counts = {}
        for annotation in self.annotations:
            counts[annotation.class_name] = counts.get(annotation.class_name, 0) + 1
        return counts


class DatasetStatistics(BaseModel):
    """Dataset statistics and metrics"""
    total_images: int = 0
    total_annotations: int = 0
    
    # Status breakdown
    unlabeled_images: int = 0
    partial_images: int = 0
    complete_images: int = 0
    verified_images: int = 0
    
    # Class distribution
    class_counts: Dict[str, int] = Field(default_factory=dict)
    class_distribution: Dict[str, float] = Field(default_factory=dict)  # Percentages
    
    # Quality metrics
    average_quality_score: Optional[float] = None
    quality_distribution: Dict[str, int] = Field(default_factory=dict)  # Quality bins
    
    # Dataset splits
    train_count: int = 0
    validation_count: int = 0
    test_count: int = 0
    
    # File size and storage
    total_size_bytes: int = 0
    average_file_size_bytes: int = 0
    
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DatasetExport(BaseModel):
    """Dataset export job"""
    export_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dataset_id: str
    
    # Export configuration
    format: DatasetFormat
    include_unlabeled: bool = False
    include_rejected: bool = False
    min_confidence: float = 0.0
    class_filter: Optional[List[str]] = None  # Export only specific classes
    
    # Dataset splits to export
    splits: List[str] = Field(default_factory=lambda: ["train", "val", "test"])
    
    # Export status
    status: str = "pending"  # pending, running, completed, failed
    progress_percent: float = 0.0
    
    # Output information
    output_path: Optional[str] = None
    output_size_bytes: int = 0
    exported_image_count: int = 0
    exported_annotation_count: int = 0
    
    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    

class TrainingData(BaseModel):
    """Complete training dataset management"""
    dataset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dataset_name: str
    description: Optional[str] = None
    version: str = "1.0"
    
    # Dataset metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"
    
    # Dataset configuration
    class_labels: List[str] = Field(default_factory=list)
    class_colors: Dict[str, str] = Field(default_factory=dict)  # Hex colors for visualization
    annotation_guidelines: Optional[str] = None
    
    # Images and annotations
    images: List[TrainingImage] = Field(default_factory=list)
    statistics: DatasetStatistics = Field(default_factory=DatasetStatistics)
    
    # Auto-collection settings
    auto_collection_enabled: bool = False
    collection_interval_seconds: int = 300  # Collect every 5 minutes
    collection_criteria: Dict[str, Any] = Field(default_factory=dict)
    max_images: Optional[int] = None  # Maximum images to collect
    
    # Export history
    export_history: List[DatasetExport] = Field(default_factory=list)
    
    # Storage settings
    storage_path: str = "/data/training"
    compression_enabled: bool = True
    backup_enabled: bool = True
    
    model_config = ConfigDict(use_enum_values=True)
    
    def add_image(self, image: TrainingImage):
        """Add a training image to the dataset"""
        self.images.append(image)
        self.last_modified = datetime.now(timezone.utc)
        self.update_statistics()
    
    def update_statistics(self):
        """Update dataset statistics"""
        stats = DatasetStatistics()
        stats.total_images = len(self.images)
        
        class_counts = {}
        total_annotations = 0
        quality_scores = []
        
        for image in self.images:
            # Count by status
            if image.label_status == LabelStatus.UNLABELED:
                stats.unlabeled_images += 1
            elif image.label_status == LabelStatus.PARTIAL:
                stats.partial_images += 1
            elif image.label_status == LabelStatus.COMPLETE:
                stats.complete_images += 1
            elif image.label_status == LabelStatus.VERIFIED:
                stats.verified_images += 1
            
            # Count annotations by class
            for annotation in image.annotations:
                class_counts[annotation.class_name] = (
                    class_counts.get(annotation.class_name, 0) + 1
                )
                total_annotations += 1
            
            # Collect quality scores
            if image.quality_score is not None:
                quality_scores.append(image.quality_score)
            
            # Count dataset splits
            if "train" in image.dataset_splits:
                stats.train_count += 1
            if "val" in image.dataset_splits:
                stats.validation_count += 1
            if "test" in image.dataset_splits:
                stats.test_count += 1
            
            # File size
            stats.total_size_bytes += image.file_size_bytes
        
        stats.total_annotations = total_annotations
        stats.class_counts = class_counts
        
        # Calculate class distribution
        if total_annotations > 0:
            stats.class_distribution = {
                cls: (count / total_annotations) * 100
                for cls, count in class_counts.items()
            }
        
        # Quality metrics
        if quality_scores:
            stats.average_quality_score = sum(quality_scores) / len(quality_scores)
        
        if len(self.images) > 0:
            stats.average_file_size_bytes = stats.total_size_bytes // len(self.images)
        
        stats.last_updated = datetime.now(timezone.utc)
        self.statistics = stats
    
    def create_export(self, format: DatasetFormat, **kwargs) -> DatasetExport:
        """Create a new dataset export"""
        export = DatasetExport(
            dataset_id=self.dataset_id,
            format=format,
            **kwargs
        )
        self.export_history.append(export)
        return export