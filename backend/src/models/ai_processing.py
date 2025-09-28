"""
AIProcessing model for LawnBerry Pi v2
AI inference results, model management, and hardware acceleration
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator


class AIAccelerator(str, Enum):
    """Available AI acceleration hardware"""
    CORAL_USB = "coral_usb"  # Google Coral USB Accelerator
    HAILO_HAT = "hailo_hat"  # Hailo-8 AI Hat
    CPU = "cpu"  # CPU-only inference (TFLite)


class ModelFormat(str, Enum):
    """AI model formats"""
    TFLITE = "tflite"  # TensorFlow Lite
    EDGE_TPU = "edge_tpu"  # Coral Edge TPU compiled
    HAILO_HEF = "hailo_hef"  # Hailo HEF format
    ONNX = "onnx"  # ONNX format
    PYTORCH = "pytorch"  # PyTorch model


class InferenceTask(str, Enum):
    """Types of AI inference tasks"""
    OBSTACLE_DETECTION = "obstacle_detection"
    GRASS_QUALITY = "grass_quality"
    BOUNDARY_DETECTION = "boundary_detection"
    NAVIGATION_AID = "navigation_aid"
    OBJECT_CLASSIFICATION = "object_classification"
    SAFETY_MONITORING = "safety_monitoring"


class ModelStatus(str, Enum):
    """AI model status"""
    LOADED = "loaded"
    LOADING = "loading"
    UNLOADED = "unloaded"
    ERROR = "error"
    COMPILING = "compiling"


class BoundingBox(BaseModel):
    """Object detection bounding box"""
    x: float  # Normalized coordinates (0.0-1.0)
    y: float
    width: float
    height: float
    
    @validator('x', 'y', 'width', 'height')
    def validate_normalized_coords(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Coordinates must be normalized between 0.0 and 1.0')
        return v


class DetectedObject(BaseModel):
    """Detected object with classification"""
    object_id: str
    class_name: str
    confidence: float  # 0.0-1.0
    bounding_box: BoundingBox
    
    # Additional properties
    distance_estimate: Optional[float] = None  # meters
    relative_bearing: Optional[float] = None  # degrees from camera center
    tracking_id: Optional[int] = None  # For object tracking across frames
    
    @validator('confidence')
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Confidence must be between 0.0 and 1.0')
        return v


class InferenceResult(BaseModel):
    """Results from AI model inference"""
    inference_id: str
    task: InferenceTask
    model_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Input information
    input_frame_id: str
    input_width: int
    input_height: int
    
    # Detection results
    detected_objects: List[DetectedObject] = Field(default_factory=list)
    
    # Classification results (for single-class tasks)
    classification_result: Optional[str] = None
    classification_confidence: Optional[float] = None
    
    # Segmentation results (if applicable)
    segmentation_mask: Optional[str] = None  # Base64 encoded mask
    
    # Performance metrics
    inference_time_ms: float = 0.0
    preprocessing_time_ms: float = 0.0
    postprocessing_time_ms: float = 0.0
    total_time_ms: float = 0.0
    
    # Model information
    model_version: str = "1.0"
    confidence_threshold: float = 0.5
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ModelInfo(BaseModel):
    """AI model information and metadata"""
    model_name: str
    model_path: str
    format: ModelFormat
    version: str = "1.0"
    
    # Model specifications
    input_width: int
    input_height: int
    input_channels: int = 3
    num_classes: int
    class_labels: List[str] = Field(default_factory=list)
    
    # Performance characteristics
    target_accelerator: AIAccelerator
    memory_usage_mb: Optional[float] = None
    typical_inference_time_ms: Optional[float] = None
    
    # Training information
    training_dataset: Optional[str] = None
    training_date: Optional[datetime] = None
    accuracy_metrics: Dict[str, float] = Field(default_factory=dict)
    
    # Status
    status: ModelStatus = ModelStatus.UNLOADED
    load_time: Optional[datetime] = None
    error_message: Optional[str] = None
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class AcceleratorStatus(BaseModel):
    """AI accelerator hardware status"""
    accelerator_type: AIAccelerator
    is_available: bool = False
    device_path: Optional[str] = None
    
    # Hardware information
    firmware_version: Optional[str] = None
    temperature: Optional[float] = None  # °C
    power_consumption: Optional[float] = None  # Watts
    
    # Performance metrics
    utilization_percent: float = 0.0
    inference_count: int = 0
    total_inference_time_ms: float = 0.0
    average_inference_time_ms: float = 0.0
    
    # Error tracking
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    
    # Environment isolation (for Coral)
    venv_path: Optional[str] = None
    venv_active: bool = False
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class AIProcessing(BaseModel):
    """Complete AI processing system state"""
    # System status
    system_enabled: bool = True
    primary_accelerator: AIAccelerator = AIAccelerator.CPU
    fallback_accelerator: AIAccelerator = AIAccelerator.CPU
    
    # Loaded models
    active_models: Dict[str, ModelInfo] = Field(default_factory=dict)
    model_cache_size_mb: float = 0.0
    max_cache_size_mb: float = 512.0
    
    # Hardware status
    accelerator_status: Dict[AIAccelerator, AcceleratorStatus] = Field(default_factory=dict)
    
    # Processing queue and performance
    queue_size: int = 0
    max_queue_size: int = 10
    processing_fps: float = 0.0
    target_fps: float = 5.0
    
    # Recent inference results
    recent_results: List[InferenceResult] = Field(default_factory=list)
    max_recent_results: int = 100
    
    # Statistics
    total_inferences: int = 0
    successful_inferences: int = 0
    failed_inferences: int = 0
    average_inference_time_ms: float = 0.0
    
    # Configuration
    confidence_threshold: float = 0.5
    nms_threshold: float = 0.4  # Non-maximum suppression
    max_detections: int = 50
    
    # Training and data collection
    training_mode_enabled: bool = False
    auto_collect_training_data: bool = False
    training_data_count: int = 0
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def get_best_accelerator(self) -> AIAccelerator:
        """Get the best available accelerator"""
        # Priority order: Coral > Hailo > CPU
        priority_order = [AIAccelerator.CORAL_USB, AIAccelerator.HAILO_HAT, AIAccelerator.CPU]
        
        for accelerator in priority_order:
            if (accelerator in self.accelerator_status and 
                self.accelerator_status[accelerator].is_available):
                return accelerator
        
        return AIAccelerator.CPU  # Fallback to CPU
    
    def add_inference_result(self, result: InferenceResult):
        """Add a new inference result and update statistics"""
        # Add to recent results
        self.recent_results.append(result)
        
        # Maintain maximum size
        if len(self.recent_results) > self.max_recent_results:
            self.recent_results.pop(0)
        
        # Update statistics
        self.total_inferences += 1
        if result.total_time_ms > 0:
            self.successful_inferences += 1
            
            # Update running average
            n = self.successful_inferences
            self.average_inference_time_ms = (
                (self.average_inference_time_ms * (n - 1) + result.total_time_ms) / n
            )
        else:
            self.failed_inferences += 1
    
    def load_model(self, model_info: ModelInfo) -> bool:
        """Load an AI model"""
        try:
            model_info.status = ModelStatus.LOADING
            model_info.load_time = datetime.now(timezone.utc)
            
            # Model loading logic would go here
            # For now, just mark as loaded
            model_info.status = ModelStatus.LOADED
            self.active_models[model_info.model_name] = model_info
            
            return True
        except Exception as e:
            model_info.status = ModelStatus.ERROR
            model_info.error_message = str(e)
            return False
    
    def get_inference_performance(self) -> Dict[str, float]:
        """Get current inference performance metrics"""
        if self.total_inferences == 0:
            return {"success_rate": 0.0, "avg_time_ms": 0.0, "fps": 0.0}
        
        success_rate = self.successful_inferences / self.total_inferences
        
        return {
            "success_rate": success_rate,
            "avg_time_ms": self.average_inference_time_ms,
            "fps": self.processing_fps,
            "queue_utilization": self.queue_size / self.max_queue_size
        }