from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class LifecycleState(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DriverInstance(BaseModel):
    driver_id: str
    driver_class: str
    hardware_resource: List[str] = Field(default_factory=list)
    simulation_mode: bool = False
    lifecycle_state: LifecycleState = LifecycleState.UNINITIALIZED
    health_status: HealthStatus = HealthStatus.UNHEALTHY
    last_health_check_ts: Optional[int] = None
    error_message: Optional[str] = None
