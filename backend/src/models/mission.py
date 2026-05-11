import uuid
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class MissionLifecycleStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class MissionWaypoint(BaseModel):
    """A single waypoint in a mission."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lat: float = Field(..., description="Latitude of the waypoint.")
    lon: float = Field(..., description="Longitude of the waypoint.")
    blade_on: bool = Field(
        default=False, description="Whether the blade is active for this waypoint."
    )
    speed: int = Field(
        default=50, ge=0, le=100, description="Mower speed at this waypoint (0-100%)."
    )

    @field_validator("lat")
    @classmethod
    def _validate_lat(cls, value: float) -> float:
        if not (-90.0 <= value <= 90.0):
            raise ValueError("lat must be between -90 and 90")
        return value

    @field_validator("lon")
    @classmethod
    def _validate_lon(cls, value: float) -> float:
        if not (-180.0 <= value <= 180.0):
            raise ValueError("lon must be between -180 and 180")
        return value


class Mission(BaseModel):
    """Represents a sequence of waypoints for the mower to follow."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Name of the mission.")
    waypoints: list[MissionWaypoint] = Field(
        default_factory=list, description="List of waypoints in the mission."
    )
    created_at: str = Field(description="ISO 8601 timestamp of when the mission was created.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Mission name cannot be empty")
        return cleaned


class MissionCreationRequest(BaseModel):
    name: str
    waypoints: list[MissionWaypoint] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Mission name cannot be empty")
        return cleaned


class MissionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    waypoints: list[MissionWaypoint] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "MissionUpdateRequest":
        if self.name is None and self.waypoints is None:
            raise ValueError("Provide name or waypoints to update.")
        return self


class MissionStatus(BaseModel):
    mission_id: str
    status: MissionLifecycleStatus
    current_waypoint_index: int | None = None
    completion_percentage: float = 0.0
    total_waypoints: int = 0
    detail: str | None = None
