from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import List, Optional


class HazardLevel(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class HazardAlert:
    alert_id: str
    hazard_level: HazardLevel
    hazard_type: str
    timestamp: datetime
    description: str
    immediate_response_required: bool = False


@dataclass
class SafetyStatus:
    is_safe: bool = True
    tilt_safe: bool = True
    collision_safe: bool = True
    tilt_angle: float = 0.0
    ground_clearance: float = 1.0
    temperature: Optional[float] = None
    active_alerts: List[HazardAlert] = None


@dataclass
class ObstacleInfo:
    obstacle_id: str
    obstacle_type: str
    x: float
    y: float
    z: float
    distance: float = 0.0
    confidence: float = 0.0
    detected_by: Optional[List[str]] = None
