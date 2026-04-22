from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

TOPIC_RE = re.compile(r"^[a-z]+(\.[a-z_]+)+$")


class PersistenceTier(str, Enum):
    CRITICAL = "critical"
    BEST_EFFORT = "best_effort"


class MessageBusEvent(BaseModel):
    topic: str
    timestamp_us: int
    payload: dict[str, Any]
    source_service: str
    message_id: str | None = Field(default=None)
    persistence_tier: PersistenceTier = Field(default=PersistenceTier.BEST_EFFORT)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str):
        if not TOPIC_RE.match(v):
            raise ValueError("Topic must follow '<category>.<subcategory>' pattern")
        return v

    @field_validator("persistence_tier")
    @classmethod
    def validate_tier(cls, v: PersistenceTier, info):
        # Enforce critical topics
        topic = info.data.get("topic", "")
        critical_prefixes = ("safety.", "nav.geofence_violation", "cmd.")
        if topic.startswith(critical_prefixes) and v != PersistenceTier.CRITICAL:
            raise ValueError("Critical topics must use persistence_tier='critical'")
        return v
