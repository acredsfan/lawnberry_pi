"""Data structures for computer vision system"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import numpy as np


class ObjectType(Enum):
    """Types of objects that can be detected"""
    PERSON = "person"
    PET = "pet"
    TOY = "toy"
    FURNITURE = "furniture"
    TREE = "tree"
    STONE = "stone"
    HOSE = "hose"
    CABLE = "cable"
    HOLE = "hole"
    SLOPE = "slope"
    WET_AREA = "wet_area"
    BOUNDARY = "boundary"
    UNKNOWN = "unknown"


class SafetyLevel(Enum):
    """Safety levels for detected objects"""
    CRITICAL = "critical"      # Immediate stop required
    HIGH = "high"             # Stop and assess
    MEDIUM = "medium"         # Slow down and monitor
    LOW = "low"               # Log and continue


class ProcessingMode(Enum):
    """Vision processing modes"""
    REAL_TIME = "real_time"
    TRAINING = "training"
    DEBUG = "debug"


@dataclass
class BoundingBox:
    """Bounding box for detected objects"""
    x: int
    y: int
    width: int
    height: int
    confidence: float
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of bounding box"""
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    @property
    def area(self) -> int:
        """Get area of bounding box"""
        return self.width * self.height


@dataclass
class DetectedObject:
    """Detected object with classification and safety information"""
    object_type: ObjectType
    bounding_box: BoundingBox
    confidence: float
    safety_level: SafetyLevel
    distance_estimate: Optional[float] = None  # meters
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_safety_critical(self) -> bool:
        """Check if object requires immediate safety response"""
        return self.safety_level == SafetyLevel.CRITICAL


@dataclass
class VisionFrame:
    """Processed camera frame with detection results"""
    timestamp: datetime
    frame_id: int
    width: int
    height: int
    objects: List[DetectedObject] = field(default_factory=list)
    processing_time_ms: float = 0.0
    model_version: str = "unknown"
    tpu_used: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_critical_objects(self) -> List[DetectedObject]:
        """Get all safety-critical objects"""
        return [obj for obj in self.objects if obj.is_safety_critical()]
    
    def get_objects_by_type(self, object_type: ObjectType) -> List[DetectedObject]:
        """Get all objects of a specific type"""
        return [obj for obj in self.objects if obj.object_type == object_type]


@dataclass
class ProcessingStats:
    """Statistics for vision processing performance"""
    total_frames: int = 0
    successful_frames: int = 0
    failed_frames: int = 0
    average_processing_time_ms: float = 0.0
    tpu_usage_percent: float = 0.0
    detection_accuracy: float = 0.0
    false_positive_rate: float = 0.0
    
    @property
    def success_rate(self) -> float:
        """Calculate processing success rate"""
        if self.total_frames == 0:
            return 0.0
        return self.successful_frames / self.total_frames


@dataclass
class TrainingImage:
    """Image collected for training purposes"""
    timestamp: datetime
    image_path: str
    width: int
    height: int
    labels: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_labeled: bool = False


@dataclass
class ModelInfo:
    """Information about a vision model"""
    name: str
    version: str
    path: str
    accuracy: float
    inference_time_ms: float
    tpu_optimized: bool
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisionConfig:
    """Configuration for vision system"""
    # Detection settings
    confidence_threshold: float = 0.5
    nms_threshold: float = 0.4
    max_detections: int = 50
    
    # Performance settings
    max_processing_time_ms: float = 100.0
    enable_tpu: bool = True
    fallback_to_cpu: bool = True
    
    # Safety settings
    person_detection_distance: float = 3.0  # meters
    pet_detection_distance: float = 1.5     # meters
    emergency_response_time_ms: float = 100.0
    
    # Training settings
    enable_continuous_learning: bool = True
    training_data_retention_days: int = 30
    min_training_samples: int = 100
    
    # Model settings
    primary_model_path: str = "models/efficientdet_d0.tflite"
    backup_model_path: str = "models/mobilenet_ssd.tflite"
    
    # Resource limits
    max_memory_usage_mb: int = 512
    max_cpu_usage_percent: float = 80.0


# Safety distance mapping for different object types
SAFETY_DISTANCES = {
    ObjectType.PERSON: 3.0,
    ObjectType.PET: 1.5,
    ObjectType.TOY: 0.5,
    ObjectType.FURNITURE: 0.8,
    ObjectType.TREE: 1.0,
    ObjectType.STONE: 0.3,
    ObjectType.HOSE: 0.2,
    ObjectType.CABLE: 0.2,
    ObjectType.HOLE: 1.0,
    ObjectType.SLOPE: 0.5,
    ObjectType.WET_AREA: 0.5,
    ObjectType.BOUNDARY: 0.2,
    ObjectType.UNKNOWN: 1.0
}

# Safety level mapping for different object types
SAFETY_LEVELS = {
    ObjectType.PERSON: SafetyLevel.CRITICAL,
    ObjectType.PET: SafetyLevel.CRITICAL,
    ObjectType.TOY: SafetyLevel.HIGH,
    ObjectType.FURNITURE: SafetyLevel.HIGH,
    ObjectType.TREE: SafetyLevel.HIGH,
    ObjectType.STONE: SafetyLevel.MEDIUM,
    ObjectType.HOSE: SafetyLevel.CRITICAL,
    ObjectType.CABLE: SafetyLevel.CRITICAL,
    ObjectType.HOLE: SafetyLevel.CRITICAL,
    ObjectType.SLOPE: SafetyLevel.HIGH,
    ObjectType.WET_AREA: SafetyLevel.MEDIUM,
    ObjectType.BOUNDARY: SafetyLevel.LOW,
    ObjectType.UNKNOWN: SafetyLevel.MEDIUM
}
