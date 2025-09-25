"""WebUIPage dataclass mirroring data-model.md specification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WebUIPage:
    """Canonical record describing one of the seven mandated WebUI experiences."""
    
    slug: str  # dashboard, map-setup, manual-control, mow-planning, ai-training, settings, docs-hub
    display_name: str
    primary_goal: str
    route_path: str  # /dashboard, /map-setup, etc.
    rest_dependencies: List[str]  # RestContract.id references
    ws_topics: List[str] = field(default_factory=list)  # WebSocketTopic.id references
    telemetry_requirements: Dict[str, Any] = field(default_factory=dict)  # cadence, alert thresholds
    simulation_support: bool = True  # Must be true per constitution
    
    def __post_init__(self):
        """Validate WebUIPage fields."""
        if not self.route_path.startswith("/"):
            raise ValueError("route_path must begin with /")
        if not self.rest_dependencies:
            raise ValueError("Every page must list at least one REST contract")
        if self.slug in ["dashboard", "manual-control", "mow-planning"] and not self.ws_topics:
            raise ValueError(f"Page {self.slug} requires live state and must include ≥1 WebSocket topic")