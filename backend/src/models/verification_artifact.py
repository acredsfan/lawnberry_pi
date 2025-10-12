"""
VerificationArtifact model for LawnBerry Pi v2
Evidence package for telemetry validation, UI walkthroughs, and documentation completion
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class ArtifactType(str, Enum):
    """Verification artifact types"""
    TELEMETRY_LOG = "telemetry_log"
    UI_SCREENCAST = "ui_screencast"
    DOC_DIFF = "doc_diff"
    PERFORMANCE_REPORT = "performance_report"
    INTEGRATION_TEST_RESULT = "integration_test_result"
    PLATFORM_DETECTION = "platform_detection"
    EVIDENCE_SNAPSHOT = "evidence_snapshot"


class PlatformInfo(BaseModel):
    """Platform detection results"""
    pi_model: str  # "PI5_8GB", "PI4B_4GB", etc.
    os_version: str
    python_version: str
    kernel_version: str
    
    # Hardware detection
    cpu_model: str
    cpu_cores: int
    cpu_frequency_mhz: int
    memory_total_gb: float
    memory_available_gb: float
    
    # GPIO and peripherals
    gpio_available: bool
    i2c_available: bool
    uart_available: bool
    
    # Detection timestamp
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    


class PerformanceMetrics(BaseModel):
    """Performance metrics for verification"""
    # Telemetry performance
    telemetry_cadence_hz: float = 0.0
    telemetry_latency_p50_ms: float = 0.0
    telemetry_latency_p95_ms: float = 0.0
    telemetry_latency_p99_ms: float = 0.0
    
    # Control latency
    control_latency_p50_ms: float = 0.0
    control_latency_p95_ms: float = 0.0
    control_latency_p99_ms: float = 0.0
    
    # System resources
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_usage_percent: float = 0.0
    
    # Network performance
    websocket_messages_per_sec: float = 0.0
    http_requests_per_sec: float = 0.0
    
    # Platform-specific thresholds
    meets_pi5_thresholds: bool = False  # ≤250ms telemetry, ≤100ms control
    meets_pi4_thresholds: bool = False  # ≤350ms telemetry, ≤100ms control
    
    # Measurement metadata
    measurement_duration_seconds: int = 0
    sample_count: int = 0
    measured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    


class TelemetrySnapshot(BaseModel):
    """Snapshot of telemetry data for evidence"""
    snapshot_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # GPS data
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_fix_type: Optional[str] = None
    gps_satellites: int = 0
    
    # IMU data
    imu_roll_deg: float = 0.0
    imu_pitch_deg: float = 0.0
    imu_yaw_deg: float = 0.0
    
    # Motor status
    drive_left_pwm: int = 0
    drive_right_pwm: int = 0
    blade_motor_enabled: bool = False
    
    # Power status
    battery_voltage: float = 0.0
    battery_current: float = 0.0
    solar_power: float = 0.0
    
    # Component health
    component_statuses: Dict[str, str] = Field(default_factory=dict)
    
    # Metadata
    platform_detected: Optional[str] = None
    sim_mode_active: bool = False
    


class VerificationArtifact(BaseModel):
    """Evidence package for feature verification"""
    # Artifact identification
    artifact_id: str
    artifact_type: ArtifactType
    
    # Location and storage
    location: str  # Path or URL
    file_size_bytes: int = 0
    checksum: Optional[str] = None  # SHA256
    
    # Content description
    summary: str
    description: Optional[str] = None
    
    # Linked requirements
    linked_requirements: List[str] = Field(default_factory=list)  # FR IDs
    linked_tasks: List[str] = Field(default_factory=list)  # Task IDs (e.g., "T009")
    
    # Verification data
    platform_info: Optional[PlatformInfo] = None
    performance_metrics: Optional[PerformanceMetrics] = None
    telemetry_snapshots: List[TelemetrySnapshot] = Field(default_factory=list)
    
    # Test results
    test_passed: bool = False
    test_failure_reason: Optional[str] = None
    test_evidence: Dict[str, Any] = Field(default_factory=dict)
    
    # Related entities
    related_telemetry_stream_id: Optional[str] = None
    related_control_session_id: Optional[str] = None
    related_documentation_id: Optional[str] = None
    
    # Metadata
    created_by: str  # operator_id or "automation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = Field(default_factory=list)
    
    model_config = ConfigDict(use_enum_values=True)
    
    def add_telemetry_snapshot(self, snapshot: TelemetrySnapshot):
        """Add a telemetry snapshot to the artifact"""
        self.telemetry_snapshots.append(snapshot)
    
    def add_requirement(self, requirement_id: str):
        """Link a functional requirement"""
        if requirement_id not in self.linked_requirements:
            self.linked_requirements.append(requirement_id)
    
    def add_task(self, task_id: str):
        """Link a task ID"""
        if task_id not in self.linked_tasks:
            self.linked_tasks.append(task_id)
    
    def compute_checksum(self, file_path: str) -> str:
        """Compute SHA256 checksum of artifact file"""
        import hashlib
        import os
        
        if not os.path.exists(file_path):
            return ""
        
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hasher.update(chunk)
        
        checksum = hasher.hexdigest()
        self.checksum = checksum
        self.file_size_bytes = os.path.getsize(file_path)
        
        return checksum


class VerificationArtifactCollection(BaseModel):
    """Collection of verification artifacts for a feature or release"""
    collection_id: str
    collection_name: str
    collection_version: str = "1.0.0"
    
    # Artifacts
    artifacts: List[VerificationArtifact] = Field(default_factory=list)
    
    # Collection metadata
    total_artifacts: int = 0
    total_size_bytes: int = 0
    
    # Verification status
    all_tests_passed: bool = False
    failed_tests: List[str] = Field(default_factory=list)
    
    # Platform coverage
    pi5_tested: bool = False
    pi4_tested: bool = False
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finalized_at: Optional[datetime] = None
    
    model_config = ConfigDict(use_enum_values=True)
    
    def add_artifact(self, artifact: VerificationArtifact):
        """Add an artifact to the collection"""
        self.artifacts.append(artifact)
        self.total_artifacts = len(self.artifacts)
        self.total_size_bytes += artifact.file_size_bytes
        
        # Update test status
        if not artifact.test_passed:
            self.failed_tests.append(artifact.artifact_id)
        
        # Update platform coverage
        if artifact.platform_info:
            if "PI5" in artifact.platform_info.pi_model:
                self.pi5_tested = True
            elif "PI4" in artifact.platform_info.pi_model:
                self.pi4_tested = True
    
    def get_artifacts_by_type(self, artifact_type: ArtifactType) -> List[VerificationArtifact]:
        """Get artifacts by type"""
        return [a for a in self.artifacts if a.artifact_type == artifact_type]
    
    def get_artifacts_by_requirement(self, requirement_id: str) -> List[VerificationArtifact]:
        """Get artifacts linked to a requirement"""
        return [
            a for a in self.artifacts
            if requirement_id in a.linked_requirements
        ]
    
    def get_artifacts_by_task(self, task_id: str) -> List[VerificationArtifact]:
        """Get artifacts linked to a task"""
        return [
            a for a in self.artifacts
            if task_id in a.linked_tasks
        ]
    
    def finalize(self):
        """Finalize the collection"""
        self.all_tests_passed = len(self.failed_tests) == 0
        self.finalized_at = datetime.now(timezone.utc)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get collection summary"""
        return {
            "collection_id": self.collection_id,
            "collection_name": self.collection_name,
            "total_artifacts": self.total_artifacts,
            "total_size_mb": round(self.total_size_bytes / (1024 * 1024), 2),
            "all_tests_passed": self.all_tests_passed,
            "failed_tests_count": len(self.failed_tests),
            "pi5_tested": self.pi5_tested,
            "pi4_tested": self.pi4_tested,
            "platform_coverage": "complete" if (self.pi5_tested and self.pi4_tested) else "partial",
            "created_at": self.created_at.isoformat(),
            "finalized": self.finalized_at is not None
        }
    
    @classmethod
    def create_for_feature(cls, feature_id: str, feature_name: str) -> 'VerificationArtifactCollection':
        """Create verification artifact collection for a feature"""
        import uuid
        
        collection = cls(
            collection_id=str(uuid.uuid4()),
            collection_name=f"Verification: {feature_name}",
            collection_version="1.0.0"
        )
        
        return collection
