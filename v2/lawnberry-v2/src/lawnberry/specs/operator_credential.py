"""OperatorCredential dataclass for authentication management."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class OperatorCredential:
    """Authentication artifact guarding WebUI access."""
    
    id: str = "operator-shared"  # Currently single shared credential
    username: str = ""
    password_hash: str = ""  # Stored securely outside spec scope
    permissions: List[str] = field(default_factory=lambda: ["view", "control", "export"])
    last_rotated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Validate OperatorCredential fields."""
        if not self.username:
            raise ValueError("username is required")
        valid_permissions = {"view", "control", "export"}
        if not set(self.permissions).issubset(valid_permissions):
            raise ValueError(f"permissions must be subset of {valid_permissions}")