from __future__ import annotations

from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field


class JobState(str, Enum):
    IDLE = "IDLE"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RetryPolicy(BaseModel):
    """Simple retry policy placeholder to satisfy package imports.

    Not used by the minimal scheduler yet, but kept for forward compatibility.
    """

    max_retries: int = Field(3, ge=0)
    backoff_seconds: int = Field(300, ge=0)


class ScheduledJob(BaseModel):
    """Lightweight Scheduled Job model for the in-process scheduler (T069)."""

    job_id: str
    name: str
    # 6-field cron with seconds, or @every syntax
    cron_schedule: str = Field(..., description="6-field cron with seconds, or @every syntax")
    state: JobState = JobState.SCHEDULED
    scheduled_start_time_us: Optional[int] = None
    last_run_time_us: Optional[int] = None
    error_message: Optional[str] = None

    # Optional fields for compatibility with broader data model
    cron_expression: Optional[str] = None
    zone_assignments: List[str] = Field(default_factory=list)
    weather_check_enabled: bool = True
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    class Config:
        use_enum_values = True
