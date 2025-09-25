"""TelemetryCadencePolicy dataclass for managing telemetry update rates."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TelemetryCadencePolicy:
    """Configuration object defining default, maximum, and minimum telemetry cadences plus triggers for runtime adjustments."""
    
    page_slug: str  # Composite key part 1
    topic: str  # Composite key part 2
    default_hz: float = 5.0
    max_hz: float = 10.0
    min_hz: float = 1.0
    boost_conditions: List[str] = field(default_factory=list)  # e.g., "manual_control_engaged", "obstacle_alert"
    degrade_conditions: List[str] = field(default_factory=list)  # e.g., "low_battery", "diagnostic_mode"
    updated_at: Optional[datetime] = None  # reflects latest operator override
    
    def __post_init__(self):
        """Validate TelemetryCadencePolicy fields."""
        if not (self.min_hz <= self.default_hz <= self.max_hz):
            raise ValueError("Must maintain min_hz <= default_hz <= max_hz")
        if not self.page_slug or not self.topic:
            raise ValueError("page_slug and topic are required for composite key")