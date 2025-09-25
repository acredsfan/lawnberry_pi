"""TelemetryStream dataclass with cadence and schema definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class TelemetryStream:
    """Streamed data published over WebSocket for real-time UI updates."""
    
    topic: str  # e.g., telemetry/updates, map/updates
    cadence_hz: float = 5.0  # Default 5Hz as per spec
    burst_max_hz: float = 10.0
    diagnostic_floor_hz: float = 1.0
    payload_schema: Optional[str] = None  # JSON Schema reference
    source_service: str = "mower-core"  # e.g., mower-core, navigation, safety
    critical: bool = False  # true triggers alert surfaces if stream stalls >3s
    
    def __post_init__(self):
        """Validate TelemetryStream fields."""
        if not (1.0 <= self.cadence_hz <= 10.0):
            raise ValueError("cadence_hz must be between 1.0 and 10.0")
        if not (1.0 <= self.burst_max_hz <= 10.0):
            raise ValueError("burst_max_hz must be between 1.0 and 10.0")
        if not (1.0 <= self.diagnostic_floor_hz <= 10.0):
            raise ValueError("diagnostic_floor_hz must be between 1.0 and 10.0")
        if self.diagnostic_floor_hz > self.cadence_hz or self.cadence_hz > self.burst_max_hz:
            raise ValueError("Must maintain diagnostic_floor_hz <= cadence_hz <= burst_max_hz")