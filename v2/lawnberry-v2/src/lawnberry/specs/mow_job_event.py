"""MowJobEvent dataclass for mowing job lifecycle events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass
class MowJobEvent:
    """Envelope describing mower job lifecycle updates emitted over WebSocket."""
    
    job_id: UUID
    sequence: int  # monotonically increasing per job
    event_type: str  # queued, started, paused, resumed, completed, failed, canceled
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    payload: Dict[str, Any] = field(default_factory=dict)  # includes progress_percent, current_zone, error_code when applicable
    
    def __post_init__(self):
        """Validate MowJobEvent fields."""
        valid_event_types = {
            "queued", "started", "paused", "resumed", 
            "completed", "failed", "canceled"
        }
        if self.event_type not in valid_event_types:
            raise ValueError(f"event_type must be one of {valid_event_types}")
        if self.sequence < 1:
            raise ValueError("sequence must be >= 1")
        
        # Validate payload based on event type
        if self.event_type in ["completed", "failed"]:
            if "progress_percent" not in self.payload:
                raise ValueError(f"{self.event_type} events must supply final progress_percent")