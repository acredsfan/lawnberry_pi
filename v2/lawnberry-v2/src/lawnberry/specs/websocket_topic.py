"""WebSocketTopic dataclass with message schema and configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class WebSocketTopic:
    """Async channel streaming state changes tied to one or more pages."""
    
    name: str  # e.g., telemetry/updates, manual/feedback
    message_schema: Dict[str, Any]  # JSON Schema reference, required
    heartbeat_interval_sec: int = 1  # default 1 second
    supports_backfill: bool = False  # dashboard and mow progress must be true
    
    def __post_init__(self):
        """Validate WebSocketTopic fields."""
        if not self.message_schema:
            raise ValueError("message_schema is required")
        if self.heartbeat_interval_sec < 1:
            raise ValueError("heartbeat_interval_sec must be >= 1")