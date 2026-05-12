import zoneinfo
from datetime import UTC, datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    days_of_week: list[int] = Field(default_factory=list)  # 0=Monday, 6=Sunday
    start_time: time | None = None
    duration_minutes: int | None = None
    enabled: bool = True
    timezone: str = "UTC"  # IANA timezone name, e.g. "America/New_York"

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            zoneinfo.ZoneInfo(v)
        except zoneinfo.ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v

    @field_validator("days_of_week", mode="before")
    @classmethod
    def validate_days_of_week(cls, v: list) -> list:
        for day in v:
            if not isinstance(day, int) or day < 0 or day > 6:
                raise ValueError(
                    f"days_of_week values must be integers 0–6 (Monday–Sunday), got {day!r}"
                )
        return v


class JobProgress(BaseModel):
    """Job execution progress tracking."""

    percentage_complete: float = 0.0
    current_zone: str | None = None
    zones_completed: list[str] = Field(default_factory=list)
    area_covered_sqm: float = 0.0
    runtime_minutes: float = 0.0


class Job(BaseModel):
    """Mowing and maintenance job definition."""

    # Job identification
    id: str
    name: str
    job_type: JobType = JobType.SCHEDULED_MOW

    # Scheduling
    schedule: SchedulePattern | None = None

    # Target areas
    zones: list[str] = Field(default_factory=list)  # Zone IDs

    # Job configuration
    priority: JobPriority = JobPriority.NORMAL
    cutting_height_mm: int | None = None
    cutting_pattern: str = "parallel"  # "parallel", "spiral", "random"
    overlap_factor: float = 0.1

    # Execution state
    status: JobStatus = JobStatus.PENDING
    progress: JobProgress | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scheduled_for: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_run: datetime | None = None
    next_run: datetime | None = None

    # Results and logs
    result_message: str | None = None
    error_message: str | None = None
    execution_logs: list[str] = Field(default_factory=list)

    # Job metadata
    enabled: bool = True
    retry_count: int = 0
    max_retries: int = 3
    timeout_minutes: int | None = None

    # Custom parameters
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)
