"""WebSocket event models implementing contracts/websocket-events.md schemas.

This module defines the Pydantic models for all WebSocket events as specified
in the WebUI Page & Hardware Alignment specification. Ensures type safety
and validation for real-time communication.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """WebSocket message types."""
    CONNECTION = "connection"
    DATA = "data"
    TELEMETRY = "telemetry"
    COMMAND = "command"
    EVENT = "event"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    CADENCE_UPDATE = "cadence_update"


class WebSocketEvent(BaseModel):
    """Base WebSocket event model."""
    type: MessageType
    topic: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_id: str = Field(...)


class ConnectionEvent(WebSocketEvent):
    """Client connection event."""
    type: MessageType = MessageType.CONNECTION
    data: Dict[str, Any] = Field(default_factory=dict)
    client_id: str
    server_time: datetime


class TelemetryEvent(WebSocketEvent):
    """Telemetry data event - 5Hz default cadence."""
    type: MessageType = MessageType.TELEMETRY
    topic: str = "telemetry/updates"
    data: "TelemetryData"


class TelemetryData(BaseModel):
    """Telemetry payload data."""
    timestamp: datetime
    battery_voltage: float = Field(ge=0.0, le=24.0)
    battery_current: Optional[float] = None
    solar_voltage: Optional[float] = None
    position: "GPSPosition"
    motor_status: "MotorStatus"
    safety_state: "SafetyState"
    blade_status: "BladeStatus"
    obstacle_distance: Optional[float] = None
    imu_heading: Optional[float] = Field(None, ge=0.0, lt=360.0)
    uptime_seconds: float
    system_load: Optional[float] = Field(None, ge=0.0, le=100.0)


class GPSPosition(BaseModel):
    """GPS position data."""
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    fix_quality: Optional[int] = Field(None, ge=0, le=9)


class MotorStatus(str, Enum):
    """Motor operational states."""
    IDLE = "idle"
    FORWARD = "forward"
    REVERSE = "reverse"
    TURNING_LEFT = "turning_left"
    TURNING_RIGHT = "turning_right"
    STOPPED = "stopped"
    ERROR = "error"


class SafetyState(str, Enum):
    """Safety system states."""
    SAFE = "safe"
    CAUTION = "caution"
    EMERGENCY_STOP = "emergency_stop"
    MANUAL_OVERRIDE = "manual_override"
    FAULT = "fault"


class BladeStatus(str, Enum):
    """Blade operational states."""
    OFF = "off"
    SPINNING = "spinning"
    STARTING = "starting"
    STOPPING = "stopping"
    FAULT = "fault"


class ManualControlEvent(WebSocketEvent):
    """Manual control command acknowledgment."""
    type: MessageType = MessageType.EVENT
    topic: str = "manual/feedback" 
    data: "ManualControlData"


class ManualControlData(BaseModel):
    """Manual control feedback data."""
    command_id: str
    command_type: "ManualCommandType"
    status: "CommandStatus"
    executed_at: datetime
    parameters: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class ManualCommandType(str, Enum):
    """Manual control command types."""
    DRIVE_FORWARD = "drive_forward"
    DRIVE_REVERSE = "drive_reverse"
    TURN_LEFT = "turn_left"
    TURN_RIGHT = "turn_right"
    STOP = "stop"
    EMERGENCY_STOP = "emergency_stop"
    BLADE_ON = "blade_on"
    BLADE_OFF = "blade_off"


class CommandStatus(str, Enum):
    """Command execution status."""
    ACCEPTED = "accepted"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class MapUpdateEvent(WebSocketEvent):
    """Map zone/boundary update event."""
    type: MessageType = MessageType.EVENT
    topic: str = "map/updates"
    data: "MapUpdateData"


class MapUpdateData(BaseModel):
    """Map update payload."""
    update_type: "MapUpdateType"
    zone_id: Optional[str] = None
    boundary_data: Optional[Dict[str, Any]] = None
    updated_by: str
    updated_at: datetime


class MapUpdateType(str, Enum):
    """Map update operation types."""
    ZONE_CREATED = "zone_created"
    ZONE_UPDATED = "zone_updated"
    ZONE_DELETED = "zone_deleted"
    BOUNDARY_UPDATED = "boundary_updated"
    EXCLUSION_ADDED = "exclusion_added"
    EXCLUSION_REMOVED = "exclusion_removed"


class MowJobEvent(WebSocketEvent):
    """Mowing job lifecycle event."""
    type: MessageType = MessageType.EVENT
    topic: str  # Will be "mow/jobs/{job_id}/events"
    data: "MowJobEventData"


class MowJobEventData(BaseModel):
    """Mowing job event payload."""
    job_id: UUID
    sequence: int = Field(ge=1)
    event_type: "MowJobEventType"
    occurred_at: datetime
    progress_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    current_zone: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    estimated_completion: Optional[datetime] = None


class MowJobEventType(str, Enum):
    """Mowing job event types."""
    QUEUED = "queued"
    STARTED = "started"
    PAUSED = "paused"
    RESUMED = "resumed"
    ZONE_COMPLETED = "zone_completed"
    COMPLETED = "completed" 
    FAILED = "failed"
    CANCELED = "canceled"


class AITrainingEvent(WebSocketEvent):
    """AI training progress event."""
    type: MessageType = MessageType.EVENT
    topic: str = "ai/training/progress"
    data: "AITrainingData"


class AITrainingData(BaseModel):
    """AI training progress payload."""
    job_id: UUID
    job_type: "AIJobType"
    status: "AIJobStatus"
    progress_percent: float = Field(ge=0.0, le=100.0)
    current_step: Optional[str] = None
    images_processed: Optional[int] = None
    total_images: Optional[int] = None
    export_formats: Optional[List[str]] = None
    artifact_urls: Optional[Dict[str, str]] = None
    error_message: Optional[str] = None


class AIJobType(str, Enum):
    """AI job types."""
    DATASET_EXPORT = "dataset_export"
    MODEL_TRAINING = "model_training"
    ANNOTATION_REVIEW = "annotation_review"


class AIJobStatus(str, Enum):
    """AI job status."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELED = "canceled"


class SettingsUpdateEvent(WebSocketEvent):
    """Settings/configuration update event."""
    type: MessageType = MessageType.EVENT
    topic: str = "settings/cadence"
    data: "SettingsUpdateData"


class SettingsUpdateData(BaseModel):
    """Settings update payload."""
    setting_type: "SettingType"
    setting_key: str
    old_value: Optional[Any] = None
    new_value: Any
    updated_by: str
    updated_at: datetime


class SettingType(str, Enum):
    """Setting category types."""
    TELEMETRY_CADENCE = "telemetry_cadence"
    HARDWARE_CONFIG = "hardware_config"
    SAFETY_LIMITS = "safety_limits"
    NAVIGATION_PARAMS = "navigation_params"
    AI_SETTINGS = "ai_settings"


class ErrorEvent(WebSocketEvent):
    """Error notification event."""
    type: MessageType = MessageType.ERROR
    data: "ErrorData"


class ErrorData(BaseModel):
    """Error event payload."""
    error_code: str
    error_message: str
    error_details: Optional[Dict[str, Any]] = None
    severity: "ErrorSeverity"
    component: Optional[str] = None
    recovery_action: Optional[str] = None


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SubscriptionMessage(BaseModel):
    """Client subscription request."""
    type: MessageType = MessageType.SUBSCRIBE
    topic: str
    client_id: Optional[str] = None


class UnsubscriptionMessage(BaseModel):
    """Client unsubscription request."""
    type: MessageType = MessageType.UNSUBSCRIBE
    topic: str
    client_id: Optional[str] = None


class CadenceUpdateMessage(BaseModel):
    """Telemetry cadence update request."""
    type: MessageType = MessageType.CADENCE_UPDATE
    cadence_hz: float = Field(ge=1.0, le=10.0)
    client_id: Optional[str] = None


# Union type for all possible WebSocket events
WebSocketEventUnion = Union[
    ConnectionEvent,
    TelemetryEvent,
    ManualControlEvent,
    MapUpdateEvent,
    MowJobEvent,
    AITrainingEvent,
    SettingsUpdateEvent,
    ErrorEvent,
    SubscriptionMessage,
    UnsubscriptionMessage,
    CadenceUpdateMessage
]