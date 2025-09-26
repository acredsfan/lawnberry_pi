"""
OperationalData model for LawnBerry Pi v2
Historical operational data and performance tracking
"""

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
import uuid


class OperationStatus(str, Enum):
    """Operational status types"""
    IDLE = "idle"
    MOWING = "mowing"
    RETURNING_HOME = "returning_home"
    CHARGING = "charging"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    EMERGENCY_STOP = "emergency_stop"


class EventType(str, Enum):
    """Types of operational events"""
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    JOB_START = "job_start"
    JOB_COMPLETE = "job_complete"
    JOB_ABORT = "job_abort"
    EMERGENCY_STOP = "emergency_stop"
    ERROR = "error"
    WARNING = "warning"
    MAINTENANCE = "maintenance"
    SENSOR_FAULT = "sensor_fault"
    POWER_EVENT = "power_event"
    WEATHER_ALERT = "weather_alert"
    USER_ACTION = "user_action"


class Severity(str, Enum):
    """Event severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class OperationalEvent(BaseModel):
    """Individual operational event record"""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Event classification
    event_type: EventType
    severity: Severity = Severity.INFO
    
    # Event details
    title: str
    description: Optional[str] = None
    source_component: Optional[str] = None
    error_code: Optional[str] = None
    
    # Context data
    system_state: Dict[str, Any] = Field(default_factory=dict)
    sensor_readings: Dict[str, Any] = Field(default_factory=dict)
    user_context: Dict[str, Any] = Field(default_factory=dict)
    
    # Resolution information
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    
    # Impact assessment
    downtime_minutes: float = 0.0
    affected_operations: List[str] = Field(default_factory=list)
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class PerformanceMetrics(BaseModel):
    """System performance metrics for a time period"""
    period_start: datetime
    period_end: datetime
    
    # Operational time tracking
    total_runtime_minutes: float = 0.0
    mowing_time_minutes: float = 0.0
    idle_time_minutes: float = 0.0
    charging_time_minutes: float = 0.0
    error_time_minutes: float = 0.0
    
    # Distance and coverage
    total_distance_m: float = 0.0
    area_covered_sqm: float = 0.0
    coverage_efficiency_percent: float = 0.0
    
    # Power consumption
    energy_consumed_wh: float = 0.0
    energy_generated_wh: float = 0.0
    net_energy_wh: float = 0.0
    battery_cycles: float = 0.0
    
    # Performance indicators
    average_speed_ms: float = 0.0
    max_speed_ms: float = 0.0
    navigation_accuracy_m: float = 0.0
    
    # Error and reliability metrics
    error_count: int = 0
    warning_count: int = 0
    emergency_stops: int = 0
    sensor_faults: int = 0
    communication_errors: int = 0
    
    # Availability metrics
    uptime_percent: float = 0.0
    availability_percent: float = 0.0  # Uptime excluding maintenance
    mtbf_hours: Optional[float] = None  # Mean time between failures
    mttr_minutes: Optional[float] = None  # Mean time to repair
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class MaintenanceRecord(BaseModel):
    """Maintenance activity record"""
    maintenance_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Maintenance details
    maintenance_type: str  # "preventive", "corrective", "emergency"
    title: str
    description: str
    
    # Work performed
    work_performed: List[str] = Field(default_factory=list)
    parts_replaced: List[str] = Field(default_factory=list)
    components_serviced: List[str] = Field(default_factory=list)
    
    # Time and effort
    duration_minutes: float = 0.0
    technician: str = "system"
    
    # Results
    issues_resolved: List[str] = Field(default_factory=list)
    next_maintenance_due: Optional[datetime] = None
    maintenance_notes: Optional[str] = None
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class JobExecution(BaseModel):
    """Individual job execution record"""
    job_execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    job_name: str
    
    # Execution timing
    scheduled_start: datetime
    actual_start: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    
    # Execution status
    status: str = "scheduled"  # scheduled, running, completed, failed, aborted
    completion_percent: float = 0.0
    
    # Performance data
    area_planned_sqm: float = 0.0
    area_completed_sqm: float = 0.0
    distance_traveled_m: float = 0.0
    execution_time_minutes: float = 0.0
    
    # Quality metrics
    coverage_quality_score: Optional[float] = None  # 0.0-1.0
    path_efficiency_score: Optional[float] = None   # 0.0-1.0
    overlap_percentage: float = 0.0
    
    # Environmental conditions
    weather_conditions: Dict[str, Any] = Field(default_factory=dict)
    battery_start_percent: float = 0.0
    battery_end_percent: float = 0.0
    
    # Issues and interruptions
    interruptions: List[Dict[str, Any]] = Field(default_factory=list)
    error_count: int = 0
    recovery_actions: List[str] = Field(default_factory=list)
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class SystemHealth(BaseModel):
    """Current system health status"""
    health_score: float = 100.0  # 0.0-100.0
    last_assessment: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Component health scores
    component_health: Dict[str, float] = Field(default_factory=dict)
    
    # Health factors
    hardware_health: float = 100.0
    software_health: float = 100.0
    battery_health: float = 100.0
    sensor_health: float = 100.0
    
    # Degradation indicators
    performance_degradation_percent: float = 0.0
    reliability_trend: str = "stable"  # "improving", "stable", "degrading"
    
    # Predictive indicators
    estimated_remaining_life_hours: Optional[float] = None
    next_maintenance_recommended: Optional[datetime] = None
    
    # Health alerts
    health_alerts: List[str] = Field(default_factory=list)
    critical_issues: List[str] = Field(default_factory=list)


class OperationalData(BaseModel):
    """Complete operational data collection"""
    # Data collection metadata
    data_collection_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collection_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Current operational status
    current_status: OperationStatus = OperationStatus.IDLE
    current_job_id: Optional[str] = None
    status_since: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Event logging
    events: List[OperationalEvent] = Field(default_factory=list)
    max_events: int = 10000  # Maximum events to keep in memory
    
    # Performance tracking
    daily_metrics: List[PerformanceMetrics] = Field(default_factory=list)
    weekly_metrics: List[PerformanceMetrics] = Field(default_factory=list)
    monthly_metrics: List[PerformanceMetrics] = Field(default_factory=list)
    
    # Job execution history
    job_executions: List[JobExecution] = Field(default_factory=list)
    
    # Maintenance history
    maintenance_records: List[MaintenanceRecord] = Field(default_factory=list)
    
    # System health
    system_health: SystemHealth = Field(default_factory=SystemHealth)
    
    # Cumulative statistics
    total_operating_hours: float = 0.0
    total_distance_km: float = 0.0
    total_area_covered_sqm: float = 0.0
    total_energy_consumed_kwh: float = 0.0
    total_jobs_completed: int = 0
    
    # Data retention settings
    event_retention_days: int = 90
    metrics_retention_days: int = 365
    job_history_retention_days: int = 180
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_event(self, event: OperationalEvent):
        """Add an operational event"""
        self.events.append(event)
        
        # Maintain event limit
        if len(self.events) > self.max_events:
            self.events.pop(0)
        
        self.last_updated = datetime.now(timezone.utc)
        
        # Update system health based on event
        if event.severity in [Severity.ERROR, Severity.CRITICAL, Severity.EMERGENCY]:
            self.system_health.health_score = max(0.0, self.system_health.health_score - 5.0)
    
    def get_events_by_type(self, event_type: EventType, 
                          hours_back: int = 24) -> List[OperationalEvent]:
        """Get events of a specific type within time window"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        return [
            event for event in self.events
            if event.event_type == event_type and event.timestamp >= cutoff_time
        ]
    
    def get_current_performance_metrics(self) -> Optional[PerformanceMetrics]:
        """Get current day's performance metrics"""
        today = datetime.now(timezone.utc).date()
        return next(
            (metrics for metrics in self.daily_metrics
             if metrics.period_start.date() == today),
            None
        )
    
    def calculate_uptime_percent(self, hours_back: int = 24) -> float:
        """Calculate uptime percentage for the given period"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        # Count error events in the period
        error_events = [
            event for event in self.events
            if (event.severity in [Severity.ERROR, Severity.CRITICAL, Severity.EMERGENCY] and
                event.timestamp >= cutoff_time)
        ]
        
        total_downtime = sum(event.downtime_minutes for event in error_events)
        total_minutes = hours_back * 60
        
        uptime_percent = ((total_minutes - total_downtime) / total_minutes) * 100
        return max(0.0, min(100.0, uptime_percent))
    
    def get_error_rate(self, hours_back: int = 24) -> float:
        """Calculate error rate (errors per hour)"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        
        error_count = len([
            event for event in self.events
            if (event.severity in [Severity.ERROR, Severity.CRITICAL] and
                event.timestamp >= cutoff_time)
        ])
        
        return error_count / hours_back if hours_back > 0 else 0.0
    
    def add_job_execution(self, job_execution: JobExecution):
        """Add a job execution record"""
        self.job_executions.append(job_execution)
        
        if job_execution.status == "completed":
            self.total_jobs_completed += 1
            self.total_distance_km += job_execution.distance_traveled_m / 1000.0
            self.total_area_covered_sqm += job_execution.area_completed_sqm
        
        self.last_updated = datetime.now(timezone.utc)
    
    def add_maintenance_record(self, maintenance: MaintenanceRecord):
        """Add a maintenance record"""
        self.maintenance_records.append(maintenance)
        
        # Improve system health after maintenance
        if maintenance.maintenance_type in ["preventive", "corrective"]:
            improvement = min(10.0, 100.0 - self.system_health.health_score)
            self.system_health.health_score += improvement
        
        self.last_updated = datetime.now(timezone.utc)
    
    def update_status(self, new_status: OperationStatus):
        """Update operational status"""
        if new_status != self.current_status:
            # Log status change event
            event = OperationalEvent(
                event_type=EventType.SYSTEM_START if new_status != OperationStatus.IDLE else EventType.SYSTEM_STOP,
                title=f"Status changed to {new_status}",
                description=f"System status changed from {self.current_status} to {new_status}",
                system_state={"previous_status": self.current_status, "new_status": new_status}
            )
            self.add_event(event)
            
            self.current_status = new_status
            self.status_since = datetime.now(timezone.utc)
    
    def cleanup_old_data(self):
        """Clean up old data based on retention policies"""
        now = datetime.now(timezone.utc)
        
        # Clean up old events
        event_cutoff = now - timedelta(days=self.event_retention_days)
        self.events = [e for e in self.events if e.timestamp >= event_cutoff]
        
        # Clean up old job executions
        job_cutoff = now - timedelta(days=self.job_history_retention_days)
        self.job_executions = [j for j in self.job_executions if j.scheduled_start >= job_cutoff]
        
        # Clean up old metrics
        metrics_cutoff = now - timedelta(days=self.metrics_retention_days)
        self.daily_metrics = [m for m in self.daily_metrics if m.period_start >= metrics_cutoff]
        self.weekly_metrics = [m for m in self.weekly_metrics if m.period_start >= metrics_cutoff]
        self.monthly_metrics = [m for m in self.monthly_metrics if m.period_start >= metrics_cutoff]