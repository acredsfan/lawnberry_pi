"""RestContract dataclass capturing REST endpoint metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RestContract:
    """REST endpoint supporting a WebUI action or data retrieval."""
    
    id: str  # URI path + method, e.g., GET /api/dashboard/state
    method: str  # GET, POST, PUT, PATCH
    path: str
    request_schema: Optional[Dict[str, Any]] = None  # JSON Schema or null when N/A
    response_schema: Dict[str, Any] = field(default_factory=dict)  # JSON Schema, required
    auth_required: bool = True  # true for all but Docs Hub
    roles_allowed: List[str] = field(default_factory=lambda: ["operator"])
    cache_ttl_seconds: Optional[int] = None  # dashboard state defaults to 2
    linked_topics: List[str] = field(default_factory=list)  # WebSocketTopic.name references
    
    def __post_init__(self):
        """Validate RestContract fields."""
        if self.method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
            raise ValueError(f"Invalid HTTP method: {self.method}")
        if not self.path.startswith("/"):
            raise ValueError("path must begin with /")
        if not self.response_schema:
            raise ValueError("response_schema is required")