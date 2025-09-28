from datetime import datetime, timezone, time
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    SCHEDULED_MOW = "scheduled_mow"
    MANUAL_MOW = "manual_mow"
    RETURN_HOME = "return_home"
    MAINTENANCE = "maintenance"
    MAPPING = "mapping"


class JobPriority(int, Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class SchedulePattern(BaseModel):
    """Schedule pattern for recurring jobs."""
    days_of_week: List[int] = Field(default_factory=list)  # 0=Monday, 6=Sunday
    start_time: Optional[time] = None
    duration_minutes: Optional[int] = None
    enabled: bool = True


class JobProgress(BaseModel):
    """Job execution progress tracking."""
    percentage_complete: float = 0.0
    current_zone: Optional[str] = None
    zones_completed: List[str] = Field(default_factory=list)
    area_covered_sqm: float = 0.0
    runtime_minutes: float = 0.0
    

class Job(BaseModel):
    """Mowing and maintenance job definition."""
    
    # Job identification
    id: str
    name: str
    job_type: JobType = JobType.SCHEDULED_MOW
    
    # Scheduling
    schedule: Optional[SchedulePattern] = None
    
    # Target areas
    zones: List[str] = Field(default_factory=list)  # Zone IDs
    
    # Job configuration
    priority: JobPriority = JobPriority.NORMAL
    cutting_height_mm: Optional[int] = None
    cutting_pattern: str = "parallel"  # "parallel", "spiral", "random"
    overlap_factor: float = 0.1
    
    # Execution state
    status: JobStatus = JobStatus.PENDING
    progress: Optional[JobProgress] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_for: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    
    # Results and logs
    result_message: Optional[str] = None
    error_message: Optional[str] = None
    execution_logs: List[str] = Field(default_factory=list)
    
    # Job metadata
    enabled: bool = True
    retry_count: int = 0
    max_retries: int = 3
    timeout_minutes: Optional[int] = None
    
    # Custom parameters
    parameters: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            time: lambda v: v.strftime('%H:%M:%S')
        }