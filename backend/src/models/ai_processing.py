"""
AIProcessing model for LawnBerry Pi v2
AI inference results, model management, and hardware acceleration
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    CUSTOM = "custom"  # JSON-configured CPU inference pipeline


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

    @field_validator("x", "y", "width", "height")
    def validate_normalized_coords(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("Coordinates must be normalized between 0.0 and 1.0")
        return v


class DetectedObject(BaseModel):
    """Detected object with classification"""

    object_id: str
    class_name: str
    confidence: float  # 0.0-1.0
    bounding_box: BoundingBox

    # Additional properties
    distance_estimate: float | None = Field(default=None, gt=0.0, le=100.0)  # meters
    relative_bearing: float | None = Field(default=None, ge=-180.0, le=180.0)
    angular_width_degrees: float | None = Field(
        default=None,
        gt=0.0,
        le=179.0,
        description="Detector box width projected through the configured camera FOV.",
    )
    tracking_id: int | None = None  # For object tracking across frames
    semantic_cost_multiplier: float = Field(
        default=1.0,
        ge=1.0,
        description="Route-cost inflation only; never reduces geometric or ToF safety.",
    )

    @field_validator("confidence")
    def validate_confidence(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("Confidence must be between 0.0 and 1.0")
        return v


class InferenceResult(BaseModel):
    """Results from AI model inference"""

    inference_id: str = Field(min_length=1)
    task: InferenceTask
    model_name: str = Field(min_length=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Input information
    input_frame_id: str = Field(min_length=1)
    input_width: int = Field(gt=0)
    input_height: int = Field(gt=0)
    source_frame_timestamp: datetime | None = None

    # Detection results
    detected_objects: list[DetectedObject] = Field(default_factory=list)

    # Classification results (for single-class tasks)
    classification_result: str | None = None
    classification_confidence: float | None = None

    # Segmentation results (if applicable)
    segmentation_mask: str | None = None  # Base64 encoded mask

    # Performance metrics
    inference_time_ms: float = Field(default=0.0, ge=0.0)
    preprocessing_time_ms: float = Field(default=0.0, ge=0.0)
    postprocessing_time_ms: float = Field(default=0.0, ge=0.0)
    total_time_ms: float = Field(default=0.0, ge=0.0)

    # Model information
    model_version: str = "1.0"
    model_runtime: str = Field(default="unknown", min_length=1)
    model_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class PerceptionSnapshot(BaseModel):
    """Freshness-qualified canonical perception result for API/WS consumers."""

    available: bool
    fresh: bool
    reason_code: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result_age_seconds: float | None = None
    max_result_age_seconds: float
    route_cost_obstacle_count: int = 0
    result: InferenceResult | None = None


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
    class_labels: list[str] = Field(default_factory=list)

    # Performance characteristics
    target_accelerator: AIAccelerator
    memory_usage_mb: float | None = None
    typical_inference_time_ms: float | None = None

    # Training information
    training_dataset: str | None = None
    training_date: datetime | None = None
    accuracy_metrics: dict[str, float] = Field(default_factory=dict)

    # Status
    status: ModelStatus = ModelStatus.UNLOADED
    load_time: datetime | None = None
    error_message: str | None = None


class AcceleratorStatus(BaseModel):
    """AI accelerator hardware status"""

    accelerator_type: AIAccelerator
    is_available: bool = False
    device_path: str | None = None

    # Hardware information
    firmware_version: str | None = None
    temperature: float | None = None  # °C
    power_consumption: float | None = None  # Watts

    # Performance metrics
    utilization_percent: float = 0.0
    inference_count: int = 0
    total_inference_time_ms: float = 0.0
    average_inference_time_ms: float = 0.0

    # Error tracking
    error_count: int = 0
    last_error: str | None = None
    last_error_time: datetime | None = None

    # Environment isolation (for Coral)
    venv_path: str | None = None
    venv_active: bool = False


class AIProcessing(BaseModel):
    """Complete AI processing system state"""

    # System status
    system_enabled: bool = True
    primary_accelerator: AIAccelerator = AIAccelerator.CPU
    fallback_accelerator: AIAccelerator = AIAccelerator.CPU

    # Loaded models
    active_models: dict[str, ModelInfo] = Field(default_factory=dict)
    model_cache_size_mb: float = 0.0
    max_cache_size_mb: float = 512.0

    # Hardware status
    accelerator_status: dict[AIAccelerator, AcceleratorStatus] = Field(default_factory=dict)

    # Processing queue and performance
    queue_size: int = 0
    max_queue_size: int = Field(default=10, gt=0)
    processing_fps: float = Field(default=0.0, ge=0.0)
    target_fps: float = Field(default=5.0, gt=0.0)

    # Recent inference results
    recent_results: list[InferenceResult] = Field(default_factory=list)
    max_recent_results: int = Field(default=100, gt=0)

    # Statistics
    total_inferences: int = 0
    successful_inferences: int = 0
    failed_inferences: int = 0
    average_inference_time_ms: float = 0.0

    # Configuration
    confidence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    nms_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    max_detections: int = Field(default=50, gt=0)

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)

    def get_best_accelerator(self) -> AIAccelerator:
        """Get the best available accelerator"""
        # Priority order: Coral > Hailo > CPU
        priority_order = [AIAccelerator.CORAL_USB, AIAccelerator.HAILO_HAT, AIAccelerator.CPU]

        for accelerator in priority_order:
            if (
                accelerator in self.accelerator_status
                and self.accelerator_status[accelerator].is_available
            ):
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
                self.average_inference_time_ms * (n - 1) + result.total_time_ms
            ) / n
        else:
            self.failed_inferences += 1

    def get_inference_performance(self) -> dict[str, float]:
        """Get current inference performance metrics"""
        if self.total_inferences == 0:
            return {"success_rate": 0.0, "avg_time_ms": 0.0, "fps": 0.0}

        success_rate = self.successful_inferences / self.total_inferences

        return {
            "success_rate": success_rate,
            "avg_time_ms": self.average_inference_time_ms,
            "fps": self.processing_fps,
            "queue_utilization": self.queue_size / self.max_queue_size,
        }
