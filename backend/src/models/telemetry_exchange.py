"""
TelemetryExchange model for LawnBerry Pi v2
Real-time data streaming and telemetry management
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, validator
import json


class ComponentId(str, Enum):
    """Hardware component identifiers"""
    IMU = "imu"
    GPS = "gps"
    POWER = "power"
    TOF_LEFT = "tof_left"
    TOF_RIGHT = "tof_right"
    BLADE_MOTOR = "blade_motor"
    DRIVE_LEFT = "drive_left"
    DRIVE_RIGHT = "drive_right"
    CORAL = "coral"
    HAILO = "hailo"
    CPU = "cpu"
    CAMERA = "camera"
    ENVIRONMENTAL = "environmental"


class ComponentStatus(str, Enum):
    """Hardware component health status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    FAULT = "fault"


class RtkFixType(str, Enum):
    """RTK GPS fix quality"""
    NO_FIX = "no_fix"
    GPS_FIX = "gps_fix"
    DGPS_FIX = "dgps_fix"
    RTK_FLOAT = "rtk_float"
    RTK_FIXED = "rtk_fixed"


class GPSData(BaseModel):
    """GPS sensor data"""
    latitude: float
    longitude: float
    altitude_m: float = 0.0
    speed_mps: float = 0.0
    heading_deg: float = 0.0
    hdop: float = 99.9  # Horizontal dilution of precision
    satellites: int = 0
    fix_type: RtkFixType = RtkFixType.NO_FIX
    rtk_status_message: Optional[str] = None  # Human-readable RTK status
    
    @validator('latitude')
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @validator('longitude')
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v


class IMUData(BaseModel):
    """IMU orientation and motion data"""
    # Quaternion orientation (w, x, y, z)
    quaternion_w: float = 1.0
    quaternion_x: float = 0.0
    quaternion_y: float = 0.0
    quaternion_z: float = 0.0
    
    # Euler angles (degrees)
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    
    # Linear acceleration (m/s²)
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    
    # Angular velocity (deg/s)
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    
    # Calibration status (0-3, 3 = fully calibrated)
    calibration_sys: int = 0
    calibration_gyro: int = 0
    calibration_accel: int = 0
    calibration_mag: int = 0


class MotorData(BaseModel):
    """Motor status data"""
    pwm_target: int = 0  # -255 to 255
    pwm_actual: int = 0
    current_amps: float = 0.0
    temperature_c: float = 0.0
    encoder_position: Optional[int] = None
    encoder_velocity: Optional[float] = None  # RPM


class PowerData(BaseModel):
    """Power system data from INA3221"""
    # Battery (Channel 1)
    battery_voltage: float = 0.0
    battery_current: float = 0.0
    battery_power: float = 0.0
    
    # Solar (Channel 3)
    solar_voltage: float = 0.0
    solar_current: float = 0.0
    solar_power: float = 0.0
    
    # Derived metrics
    battery_soc_percent: Optional[float] = None  # State of charge estimate
    battery_health: ComponentStatus = ComponentStatus.HEALTHY


class ToFData(BaseModel):
    """Time-of-Flight sensor data"""
    distance_mm: int = 0
    range_status: str = "valid"  # valid, out_of_range, signal_fail
    signal_rate: float = 0.0


class HardwareTelemetryStream(BaseModel):
    """Real-time snapshot of hardware sensor values and status"""
    # Timestamp and identification
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    component_id: ComponentId
    
    # Component value (variant based on component_id)
    value: Union[float, int, str, Dict[str, Any]] = Field(default=0.0)
    
    # Component health
    status: ComponentStatus = ComponentStatus.HEALTHY
    latency_ms: float = 0.0
    
    # Component-specific structured data
    gps_data: Optional[GPSData] = None
    imu_data: Optional[IMUData] = None
    motor_data: Optional[MotorData] = None
    power_data: Optional[PowerData] = None
    tof_data: Optional[ToFData] = None
    
    # Generic metadata (JSON for flexibility)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Verification artifact reference
    verification_artifact_id: Optional[str] = None
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    @validator('latency_ms')
    def validate_latency(cls, v):
        if v < 0 or v > 10000:  # 10 second max
            raise ValueError('Latency must be between 0 and 10000 ms')
        return v


class TelemetryTopic(str, Enum):
    """Available telemetry topics"""
    TELEMETRY_UPDATES = "telemetry/updates"
    SYSTEM_STATUS = "system/status"
    SENSOR_DATA = "sensors/data"
    NAVIGATION_STATE = "navigation/state"
    MOTOR_CONTROL = "motor/control"
    POWER_STATUS = "power/status"
    CAMERA_FRAMES = "camera/frames"
    AI_RESULTS = "ai/results"
    SAFETY_ALERTS = "safety/alerts"
    MAP_UPDATES = "map/updates"
    JOB_STATUS = "jobs/status"
    LOGS = "system/logs"


class MessagePriority(str, Enum):
    """Message priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class StreamStatus(str, Enum):
    """Telemetry stream status"""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    THROTTLED = "throttled"


class TelemetryMessage(BaseModel):
    """Individual telemetry message"""
    message_id: str
    topic: TelemetryTopic
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Message content
    data: Dict[str, Any] = Field(default_factory=dict)
    message_type: str = "data"  # "data", "event", "alert", "command"
    
    # Message metadata
    priority: MessagePriority = MessagePriority.NORMAL
    sequence_number: int = 0
    source_service: str = "unknown"
    
    # Quality of service
    retain: bool = False  # Should message be retained for late subscribers
    expiry_seconds: Optional[int] = None  # Message expiry time
    
    # Client targeting
    target_clients: Optional[List[str]] = None  # Specific client IDs (None = all)
    client_filter: Optional[Dict[str, Any]] = None  # Filter criteria
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def to_websocket_message(self) -> str:
        """Convert to WebSocket JSON message"""
        return json.dumps({
            "event": "telemetry.data",
            "topic": self.topic,
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
            "priority": self.priority,
            "data": self.data
        })


class StreamConfiguration(BaseModel):
    """Configuration for a telemetry stream"""
    topic: TelemetryTopic
    enabled: bool = True
    
    # Rate limiting
    cadence_hz: float = 5.0  # Default 5Hz
    burst_max_hz: float = 10.0  # Maximum burst rate
    burst_duration_ms: int = 1000  # Burst window
    
    # Quality thresholds
    diagnostic_floor_hz: float = 1.0  # Minimum acceptable rate
    critical_stream: bool = False  # Alert if stream stalls >3s
    
    # Message handling
    buffer_size: int = 100  # Messages to buffer
    compression_enabled: bool = False
    batch_messages: bool = False
    batch_size: int = 10
    
    # Client management
    max_subscribers: int = 50
    subscriber_timeout_seconds: int = 30
    
    # Data filtering
    payload_schema: Optional[str] = None  # JSON schema reference
    data_filters: List[str] = Field(default_factory=list)  # Filter expressions
    
    @validator('cadence_hz', 'burst_max_hz', 'diagnostic_floor_hz')
    def validate_frequencies(cls, v):
        if v <= 0 or v > 100:
            raise ValueError('Frequency must be between 0.1 and 100 Hz')
        return v


class ClientSubscription(BaseModel):
    """Client subscription to telemetry topics"""
    client_id: str
    topic: TelemetryTopic
    subscribed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Subscription preferences  
    cadence_override_hz: Optional[float] = None  # Client-specific cadence
    priority_filter: Optional[MessagePriority] = None  # Minimum priority
    data_fields: Optional[List[str]] = None  # Specific fields to include
    
    # Quality of service
    guaranteed_delivery: bool = False
    message_history_count: int = 0  # Messages to backfill on subscribe
    
    # Statistics
    messages_sent: int = 0
    messages_dropped: int = 0
    last_message_time: Optional[datetime] = None
    connection_errors: int = 0


class StreamStatistics(BaseModel):
    """Statistics for a telemetry stream"""
    topic: TelemetryTopic
    
    # Message counters
    messages_published: int = 0
    messages_delivered: int = 0
    messages_dropped: int = 0
    messages_buffered: int = 0
    
    # Rate statistics
    current_rate_hz: float = 0.0
    average_rate_hz: float = 0.0
    peak_rate_hz: float = 0.0
    
    # Subscriber statistics
    active_subscribers: int = 0
    total_subscribers: int = 0
    
    # Performance metrics
    average_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    buffer_utilization_percent: float = 0.0
    
    # Error tracking
    error_count: int = 0
    last_error_time: Optional[datetime] = None
    last_error_message: Optional[str] = None
    
    # Time tracking
    stream_start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_message_time: Optional[datetime] = None
    last_reset_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class TelemetryHub(BaseModel):
    """Central telemetry hub managing all streams"""
    hub_id: str = "primary"
    
    # Stream management
    streams: Dict[TelemetryTopic, StreamConfiguration] = Field(default_factory=dict)
    stream_statistics: Dict[TelemetryTopic, StreamStatistics] = Field(default_factory=dict)
    
    # Client management
    connected_clients: Dict[str, datetime] = Field(default_factory=dict)
    client_subscriptions: List[ClientSubscription] = Field(default_factory=list)
    
    # Global settings
    global_rate_limit_hz: float = 50.0  # Total message rate limit
    max_concurrent_clients: int = 100
    message_retention_hours: int = 24
    
    # Health monitoring
    hub_status: StreamStatus = StreamStatus.ACTIVE
    health_check_interval_seconds: int = 30
    last_health_check: Optional[datetime] = None
    
    # Message queue
    pending_messages: List[TelemetryMessage] = Field(default_factory=list)
    max_queue_size: int = 10000
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_stream(self, topic: TelemetryTopic, config: StreamConfiguration):
        """Add or update a stream configuration"""
        self.streams[topic] = config
        if topic not in self.stream_statistics:
            self.stream_statistics[topic] = StreamStatistics(topic=topic)
    
    def subscribe_client(self, client_id: str, topic: TelemetryTopic, **kwargs) -> bool:
        """Subscribe a client to a topic"""
        if topic not in self.streams or not self.streams[topic].enabled:
            return False
        
        # Check if already subscribed
        existing = next(
            (sub for sub in self.client_subscriptions 
             if sub.client_id == client_id and sub.topic == topic),
            None
        )
        
        if existing:
            return True  # Already subscribed
        
        # Check subscriber limits
        topic_subscribers = sum(
            1 for sub in self.client_subscriptions if sub.topic == topic
        )
        if topic_subscribers >= self.streams[topic].max_subscribers:
            return False
        
        # Add subscription
        subscription = ClientSubscription(
            client_id=client_id,
            topic=topic,
            **kwargs
        )
        self.client_subscriptions.append(subscription)
        
        # Update statistics
        if topic in self.stream_statistics:
            self.stream_statistics[topic].active_subscribers += 1
            self.stream_statistics[topic].total_subscribers += 1
        
        return True
    
    def unsubscribe_client(self, client_id: str, topic: TelemetryTopic = None):
        """Unsubscribe client from topic(s)"""
        if topic:
            # Unsubscribe from specific topic
            self.client_subscriptions = [
                sub for sub in self.client_subscriptions
                if not (sub.client_id == client_id and sub.topic == topic)
            ]
            if topic in self.stream_statistics:
                self.stream_statistics[topic].active_subscribers = max(
                    0, self.stream_statistics[topic].active_subscribers - 1
                )
        else:
            # Unsubscribe from all topics
            removed_topics = set()
            self.client_subscriptions = [
                sub for sub in self.client_subscriptions
                if sub.client_id != client_id or removed_topics.add(sub.topic)
            ]
            # Update statistics for all affected topics
            for topic in removed_topics:
                if topic in self.stream_statistics:
                    self.stream_statistics[topic].active_subscribers = max(
                        0, self.stream_statistics[topic].active_subscribers - 1
                    )
    
    def publish_message(self, message: TelemetryMessage) -> bool:
        """Publish a message to subscribers"""
        if len(self.pending_messages) >= self.max_queue_size:
            return False  # Queue full
        
        self.pending_messages.append(message)
        
        # Update statistics
        if message.topic in self.stream_statistics:
            stats = self.stream_statistics[message.topic]
            stats.messages_published += 1
            stats.last_message_time = message.timestamp
        
        return True
    
    def get_topic_subscribers(self, topic: TelemetryTopic) -> List[ClientSubscription]:
        """Get all subscribers for a topic"""
        return [
            sub for sub in self.client_subscriptions
            if sub.topic == topic
        ]


class TelemetryExchange(BaseModel):
    """Complete telemetry exchange system"""
    # Primary telemetry hub
    hub: TelemetryHub = Field(default_factory=TelemetryHub)
    
    # System-wide telemetry settings
    telemetry_enabled: bool = True
    debug_mode: bool = False
    log_all_messages: bool = False
    
    # Performance monitoring
    system_load_percent: float = 0.0
    memory_usage_mb: float = 0.0
    network_utilization_percent: float = 0.0
    
    # Historical data
    message_history: List[TelemetryMessage] = Field(default_factory=list)
    max_history_size: int = 1000
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    @classmethod
    def create_default_exchange(cls) -> 'TelemetryExchange':
        """Create telemetry exchange with default streams"""
        exchange = cls()
        
        # Configure default streams
        default_streams = [
            (TelemetryTopic.TELEMETRY_UPDATES, 5.0, True),
            (TelemetryTopic.SYSTEM_STATUS, 1.0, False),
            (TelemetryTopic.SENSOR_DATA, 10.0, True),
            (TelemetryTopic.NAVIGATION_STATE, 2.0, False),
            (TelemetryTopic.POWER_STATUS, 1.0, False),
            (TelemetryTopic.SAFETY_ALERTS, 1.0, True),
        ]
        
        for topic, cadence, critical in default_streams:
            config = StreamConfiguration(
                topic=topic,
                cadence_hz=cadence,
                critical_stream=critical
            )
            exchange.hub.add_stream(topic, config)
        
        return exchange