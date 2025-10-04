from __future__ import annotations

"""LogBundle model (T083).

Represents a generated diagnostic bundle with references to included files.
"""

from datetime import datetime
from typing import List
from pydantic import BaseModel, Field


class LogBundle(BaseModel):
    bundle_id: str
    created_at_ts: datetime = Field(default_factory=datetime.utcnow)
    included_files: List[str] = Field(default_factory=list)
    size_bytes: int = 0
    trigger_reason: str = "manual"
