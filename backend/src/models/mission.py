from pydantic import BaseModel, Field
from typing import List, Optional
import uuid

class MissionWaypoint(BaseModel):
    """A single waypoint in a mission."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lat: float = Field(..., description="Latitude of the waypoint.")
    lon: float = Field(..., description="Longitude of the waypoint.")
    blade_on: bool = Field(default=False, description="Whether the blade is active for this waypoint.")
    speed: int = Field(default=50, ge=0, le=100, description="Mower speed at this waypoint (0-100%).")

class Mission(BaseModel):
    """Represents a sequence of waypoints for the mower to follow."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Name of the mission.")
    waypoints: List[MissionWaypoint] = Field(default_factory=list, description="List of waypoints in the mission.")
    created_at: str = Field(description="ISO 8601 timestamp of when the mission was created.")
    
class MissionCreationRequest(BaseModel):
    name: str
    waypoints: List[MissionWaypoint]

class MissionStatus(BaseModel):
    mission_id: str
    status: str # e.g., "running", "paused", "completed", "aborted"
    current_waypoint_index: Optional[int] = None
    completion_percentage: float = 0.0
