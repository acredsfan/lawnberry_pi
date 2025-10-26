"""
CameraStream model for LawnBerry Pi v2
Camera frame data and streaming metadata
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict, PrivateAttr
import base64


class CameraMode(str, Enum):
    """Camera operation modes"""
    STREAMING = "streaming"  # Continuous streaming
    SNAPSHOT = "snapshot"  # Single frame capture
    RECORDING = "recording"  # Video recording
    OFFLINE = "offline"  # Camera not available
    ERROR = "error"  # Camera error state


class FrameFormat(str, Enum):
    """Frame data formats"""
    JPEG = "jpeg"
    PNG = "png"
    RGB = "rgb"
    YUV = "yuv"
    H264 = "h264"  # For video streams


class StreamQuality(str, Enum):
    """Stream quality presets"""
    LOW = "low"      # 320x240 @ 15fps
    MEDIUM = "medium"  # 640x480 @ 15fps
    HIGH = "high"    # 1280x720 @ 30fps
    ULTRA = "ultra"  # 1920x1080 @ 30fps


class CameraCapabilities(BaseModel):
    """Camera hardware capabilities"""
    max_resolution_width: int = 1920
    max_resolution_height: int = 1080
    max_framerate: float = 30.0
    supported_formats: List[FrameFormat] = Field(default_factory=lambda: [
        FrameFormat.JPEG, FrameFormat.PNG, FrameFormat.RGB
    ])
    has_autofocus: bool = False
    has_optical_zoom: bool = False
    sensor_type: str = "Pi Camera v2"


class FrameMetadata(BaseModel):
    """Individual frame metadata"""
    frame_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence_number: int = 0
    
    # Frame properties
    width: int
    height: int
    format: FrameFormat = FrameFormat.JPEG
    size_bytes: int = 0
    
    # Camera settings at capture
    exposure_time: Optional[float] = None  # microseconds
    iso: Optional[int] = None
    brightness: Optional[float] = None  # -1.0 to 1.0
    contrast: Optional[float] = None  # -1.0 to 1.0
    saturation: Optional[float] = None  # -1.0 to 1.0
    
    # Quality metrics
    sharpness_score: Optional[float] = None  # 0.0 to 1.0
    noise_level: Optional[float] = None  # 0.0 to 1.0
    motion_blur: Optional[float] = None  # 0.0 to 1.0


class CameraFrame(BaseModel):
    """Single camera frame with data"""
    metadata: FrameMetadata
    data: Optional[str] = None  # Base64 encoded frame data
    
    # Processing flags
    processed_for_ai: bool = False
    ai_annotations: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Storage information
    stored_to_disk: bool = False
    file_path: Optional[str] = None
    checksum: Optional[str] = None

    _raw_cache: Optional[bytes] = PrivateAttr(default=None)
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    
    def set_frame_data(self, frame_bytes: bytes):
        """Set frame data from raw bytes"""
        self._raw_cache = bytes(frame_bytes)
        self.data = base64.b64encode(frame_bytes).decode('utf-8')
        self.metadata.size_bytes = len(frame_bytes)
    
    def get_frame_data(self) -> Optional[bytes]:
        """Get frame data as raw bytes"""
        if self._raw_cache is not None:
            return self._raw_cache
        if self.data:
            try:
                raw = base64.b64decode(self.data)
            except Exception:
                return None
            self._raw_cache = raw
            return raw
        return None


class StreamStatistics(BaseModel):
    """Streaming performance statistics"""
    frames_captured: int = 0
    frames_dropped: int = 0
    frames_processed: int = 0
    bytes_transmitted: int = 0
    
    # Performance metrics
    current_fps: float = 0.0
    average_fps: float = 0.0
    target_fps: float = 15.0
    
    # Timing statistics
    average_frame_time_ms: float = 0.0
    max_frame_time_ms: float = 0.0
    min_frame_time_ms: float = 0.0
    average_processing_time_ms: float = 0.0
    
    # Quality metrics
    average_frame_size: int = 0
    compression_ratio: float = 0.0
    
    # Error tracking
    encoding_errors: int = 0
    transmission_errors: int = 0
    buffer_overruns: int = 0
    
    last_reset: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CameraConfiguration(BaseModel):
    """Camera configuration settings"""
    # Resolution and format
    width: int = 1280
    height: int = 720
    framerate: float = 15.0
    format: FrameFormat = FrameFormat.JPEG
    quality: StreamQuality = StreamQuality.MEDIUM
    
    # Image processing
    auto_exposure: bool = True
    auto_white_balance: bool = True
    brightness: float = 0.0  # -1.0 to 1.0
    contrast: float = 0.0  # -1.0 to 1.0
    saturation: float = 0.0  # -1.0 to 1.0
    sharpness: float = 0.0  # -1.0 to 1.0
    
    # Advanced settings
    denoise: bool = True
    flip_horizontal: bool = False
    flip_vertical: bool = False
    rotation: int = 0  # 0, 90, 180, 270 degrees
    
    # Streaming settings
    buffer_size: int = 10  # Number of frames to buffer
    streaming_enabled: bool = True
    recording_enabled: bool = False
    
    @field_validator('width', 'height')
    def validate_resolution(cls, v):
        if v <= 0 or v > 4096:
            raise ValueError('Resolution must be between 1 and 4096')
        return v
    
    @field_validator('framerate')
    def validate_framerate(cls, v):
        if v <= 0 or v > 60:
            raise ValueError('Framerate must be between 0.1 and 60 fps')
        return v
    
    @field_validator('brightness', 'contrast', 'saturation', 'sharpness')
    def validate_image_adjustments(cls, v):
        if not (-1.0 <= v <= 1.0):
            raise ValueError('Image adjustments must be between -1.0 and 1.0')
        return v
    
    @field_validator('rotation')
    def validate_rotation(cls, v):
        if v not in [0, 90, 180, 270]:
            raise ValueError('Rotation must be 0, 90, 180, or 270 degrees')
        return v


class CameraStream(BaseModel):
    """Complete camera stream state and configuration"""
    # Stream identification
    stream_id: str = "primary"
    device_path: str = "/dev/video0"
    
    # Current status
    mode: CameraMode = CameraMode.OFFLINE
    is_active: bool = False
    last_frame_time: Optional[datetime] = None
    
    # Configuration and capabilities
    configuration: CameraConfiguration = Field(default_factory=CameraConfiguration)
    capabilities: CameraCapabilities = Field(default_factory=CameraCapabilities)
    
    # Current frame and statistics
    current_frame: Optional[CameraFrame] = None
    statistics: StreamStatistics = Field(default_factory=StreamStatistics)
    
    # IPC and service information
    service_endpoint: str = "unix:///tmp/camera-stream.sock"
    client_count: int = 0
    max_clients: int = 5
    
    # Storage and AI processing
    auto_save_frames: bool = False
    save_interval_seconds: int = 300  # Save frame every 5 minutes
    ai_processing_enabled: bool = True
    
    # Error handling
    error_message: Optional[str] = None
    error_count: int = 0
    last_error_time: Optional[datetime] = None
    restart_count: int = 0
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(use_enum_values=True)
    
    def update_statistics(self, frame_duration_ms: float, processing_time_ms: float | None = None):
        """Update streaming statistics with new frame timing."""
        stats = self.statistics
        stats.frames_captured += 1

        # Update frame duration metrics
        if stats.frames_captured == 1:
            stats.min_frame_time_ms = frame_duration_ms
            stats.max_frame_time_ms = frame_duration_ms
            stats.average_frame_time_ms = frame_duration_ms
        else:
            stats.min_frame_time_ms = min(stats.min_frame_time_ms, frame_duration_ms)
            stats.max_frame_time_ms = max(stats.max_frame_time_ms, frame_duration_ms)
            n = stats.frames_captured
            stats.average_frame_time_ms = (
                (stats.average_frame_time_ms * (n - 1) + frame_duration_ms) / n
            )

        # Track processing time separately when provided
        if processing_time_ms is not None:
            if stats.frames_captured == 1:
                stats.average_processing_time_ms = processing_time_ms
            else:
                n = stats.frames_captured
                stats.average_processing_time_ms = (
                    (stats.average_processing_time_ms * (n - 1) + processing_time_ms) / n
                )

        # Derive FPS metrics based on actual frame duration
        if frame_duration_ms > 0:
            stats.current_fps = 1000.0 / frame_duration_ms
        else:
            stats.current_fps = self.configuration.framerate

        if stats.average_frame_time_ms > 0:
            stats.average_fps = 1000.0 / stats.average_frame_time_ms
        else:
            stats.average_fps = self.configuration.framerate

        stats.target_fps = self.configuration.framerate
    
    def is_healthy(self) -> bool:
        """Check if camera stream is operating normally"""
        if not self.is_active or self.mode in [CameraMode.OFFLINE, CameraMode.ERROR]:
            return False
        
        # Check if we've received frames recently
        if self.last_frame_time:
            time_since_frame = datetime.now(timezone.utc) - self.last_frame_time
            if time_since_frame.total_seconds() > 10.0:  # No frame in 10 seconds
                return False
        
        # Check error rate
        if (self.statistics.frames_captured > 100 and 
            self.statistics.frames_dropped / self.statistics.frames_captured > 0.1):
            return False  # >10% drop rate
        
        return True