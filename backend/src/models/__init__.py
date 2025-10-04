"""
Models package for LawnBerry Pi v2
Pydantic models for all system entities
"""

from .sensor_data import (
    SensorData, SensorReading, GpsReading, ImuReading, TofReading, 
    EnvironmentalReading, PowerReading, SensorType, SensorStatus, GpsMode
)
from .navigation_state import (
    NavigationState, Position, Waypoint, Obstacle, CoverageCell,
    NavigationMode, PathStatus
)
from .motor_control import (
    MotorControl, DriveCommand, BladeCommand, EncoderFeedback, MotorDiagnostics,
    DriveController, ControlMode, MotorStatus
)
from .power_management import (
    PowerManagement, BatteryStatus, SolarStatus, INA3221Reading, PowerBudget,
    PowerMode, BatteryChemistry, ChargingStatus
)
from .camera_stream import (
    CameraStream, CameraFrame, FrameMetadata, StreamStatistics, CameraConfiguration,
    CameraMode, FrameFormat, StreamQuality, CameraCapabilities
)
from .ai_processing import (
    AIProcessing, InferenceResult, DetectedObject, ModelInfo, AcceleratorStatus,
    AIAccelerator, ModelFormat, InferenceTask, ModelStatus, BoundingBox
)
from .training_data import (
    TrainingData, TrainingImage, ObjectAnnotation, DatasetStatistics, DatasetExport,
    DatasetFormat, LabelStatus, AnnotationType, BoundingBoxAnnotation
)
from .webui_contracts import (
    WebUIPageContracts, WebUIPageContract, DataDependency, TelemetryRequirement,
    WebUIPageSlug, AuthRequirement, DataDependencyType, PerformanceMetrics,
    DocumentationBundle, DocumentationFile, DocumentationType
)
from .telemetry_exchange import (
    TelemetryExchange, TelemetryHub, TelemetryMessage, StreamConfiguration,
    ClientSubscription, StreamStatistics, TelemetryTopic, MessagePriority, StreamStatus,
    HardwareTelemetryStream, ComponentId, ComponentStatus, RtkFixType,
    GPSData, IMUData, MotorData, PowerData, ToFData
)
from .zone import (
    Zone, ZoneType, Point, ZoneSettings, ZoneStatistics,
    MapConfiguration, MapMarker, MarkerType, MapProvider
)
from .control_session import (
    ControlSession, ControlCommand, ControlAuditEntry, EmergencyState,
    ControlCommandType, ControlCommandResult, EmergencyStatus, SafetyInterlock
)
from .user_session import (
    UserSession, SessionActivity, UserPreferences, SecurityContext, WebSocketConnection,
    SessionStatus, UserRole, AuthenticationMethod, ConnectionType, Permission
)
from .hardware_baseline import (
    HardwareBaseline, HardwareComponent, GPIOPinAssignment, I2CDeviceMap,
    UARTAssignment, PowerSpecification, RaspberryPiModel, GpsModuleType,
    DriveControllerType, AIAcceleratorType, ComponentStatus
)
from .system_configuration import (
    SystemConfiguration, SensorCalibration, NavigationSettings, SafetyThresholds,
    UIPreferences, BrandingReference, NetworkConfiguration, OperationalMode,
    GpsModeConfig, DriveControllerConfig, AIRunnerPreference, LogLevel,
    SettingsProfile, TelemetrySettings, ControlSettings, MapsSettings,
    CameraSettings, AISettings, SystemSettings
)
from .operational_data import (
    OperationalData, OperationalEvent, PerformanceMetrics, MaintenanceRecord,
    JobExecution, SystemHealth, OperationStatus, EventType, Severity
)
from .verification_artifact import (
    VerificationArtifact, VerificationArtifactCollection, ArtifactType,
    PlatformInfo, PerformanceMetrics as VerificationPerformanceMetrics,
    TelemetrySnapshot
)
from .navigation_waypoint import NavigationWaypoint
from .sensor_reading import SensorReadingV2
from .geofence import Geofence, LatLng
from .scheduled_job import ScheduledJob, JobState, RetryPolicy
from .coverage_pattern import CoveragePattern
from .log_bundle import LogBundle

__all__ = [
    # Sensor Data
    "SensorData", "SensorReading", "GpsReading", "ImuReading", "TofReading",
    "EnvironmentalReading", "PowerReading", "SensorType", "SensorStatus", "GpsMode",
    
    # Navigation
    "NavigationState", "Position", "Waypoint", "Obstacle", "CoverageCell",
    "NavigationMode", "PathStatus",
    
    # Motor Control
    "MotorControl", "DriveCommand", "BladeCommand", "EncoderFeedback", "MotorDiagnostics",
    "DriveController", "ControlMode", "MotorStatus",
    
    # Power Management
    "PowerManagement", "BatteryStatus", "SolarStatus", "INA3221Reading", "PowerBudget",
    "PowerMode", "BatteryChemistry", "ChargingStatus",
    
    # Camera Stream
    "CameraStream", "CameraFrame", "FrameMetadata", "StreamStatistics", "CameraConfiguration",
    "CameraMode", "FrameFormat", "StreamQuality", "CameraCapabilities",
    
    # AI Processing
    "AIProcessing", "InferenceResult", "DetectedObject", "ModelInfo", "AcceleratorStatus",
    "AIAccelerator", "ModelFormat", "InferenceTask", "ModelStatus", "BoundingBox",
    
    # Training Data
    "TrainingData", "TrainingImage", "ObjectAnnotation", "DatasetStatistics", "DatasetExport",
    "DatasetFormat", "LabelStatus", "AnnotationType", "BoundingBoxAnnotation",
    
    # WebUI Contracts
    "WebUIPageContracts", "WebUIPageContract", "DataDependency", "TelemetryRequirement",
    "WebUIPageSlug", "AuthRequirement", "DataDependencyType", "PerformanceMetrics",
    "DocumentationBundle", "DocumentationFile", "DocumentationType",
    
    # Telemetry Exchange
    "TelemetryExchange", "TelemetryHub", "TelemetryMessage", "StreamConfiguration",
    "ClientSubscription", "StreamStatistics", "TelemetryTopic", "MessagePriority", "StreamStatus",
    "HardwareTelemetryStream", "ComponentId", "ComponentStatus", "RtkFixType",
    "GPSData", "IMUData", "MotorData", "PowerData", "ToFData",
    
    # Zones and Map Configuration
    "Zone", "ZoneType", "Point", "ZoneSettings", "ZoneStatistics",
    "MapConfiguration", "MapMarker", "MarkerType", "MapProvider",
    
    # Control Session
    "ControlSession", "ControlCommand", "ControlAuditEntry", "EmergencyState",
    "ControlCommandType", "ControlCommandResult", "EmergencyStatus", "SafetyInterlock",
    
    # User Session
    "UserSession", "SessionActivity", "UserPreferences", "SecurityContext", "WebSocketConnection",
    "SessionStatus", "UserRole", "AuthenticationMethod", "ConnectionType", "Permission",
    
    # Hardware Baseline
    "HardwareBaseline", "HardwareComponent", "GPIOPinAssignment", "I2CDeviceMap",
    "UARTAssignment", "PowerSpecification", "RaspberryPiModel", "GpsModuleType",
    "DriveControllerType", "AIAcceleratorType", "ComponentStatus",
    
    # System Configuration
    "SystemConfiguration", "SensorCalibration", "NavigationSettings", "SafetyThresholds",
    "UIPreferences", "BrandingReference", "NetworkConfiguration", "OperationalMode",
    "GpsModeConfig", "DriveControllerConfig", "AIRunnerPreference", "LogLevel",
    "SettingsProfile", "TelemetrySettings", "ControlSettings", "MapsSettings",
    "CameraSettings", "AISettings", "SystemSettings",
    
    # Operational Data
    "OperationalData", "OperationalEvent", "PerformanceMetrics", "MaintenanceRecord",
    "JobExecution", "SystemHealth", "OperationStatus", "EventType", "Severity",
    
    # Verification Artifacts
    "VerificationArtifact", "VerificationArtifactCollection", "ArtifactType",
    "PlatformInfo", "VerificationPerformanceMetrics", "TelemetrySnapshot"
]

# Additional exports for Phase 4/6/7 models
__all__ += [
    "NavigationWaypoint",
    "SensorReadingV2",
    "Geofence",
    "LatLng",
    "ScheduledJob",
    "JobState",
    "RetryPolicy",
    "CoveragePattern",
    "LogBundle",
]

