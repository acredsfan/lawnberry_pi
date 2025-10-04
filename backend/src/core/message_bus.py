from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.src.models.message_bus_event import MessageBusEvent, PersistenceTier


Handler = Callable[[Dict[str, Any]], Awaitable[None]]


class MessageBus:
    def __init__(self, persistence: Optional[Any] = None) -> None:
        self._subscriptions: Dict[str, List[Handler]] = {}
        self._persistence = persistence

    async def subscribe(self, topic: str, handler: Handler, persistent: bool = False) -> None:
        self._subscriptions.setdefault(topic, []).append(handler)

    async def publish(self, topic: str, payload: Dict[str, Any], persistent: bool = False) -> None:
        evt = MessageBusEvent(
            topic=topic,
            timestamp_us=int(time.time() * 1_000_000),
            payload=payload,
            source_service="backend",
            persistence_tier=PersistenceTier.CRITICAL if persistent else PersistenceTier.BEST_EFFORT,
        )

        # persist if requested and persistence available
        if persistent and self._persistence is not None:
            self._persistence.save(evt.topic, evt.timestamp_us, evt.payload)

        for handler in self._subscriptions.get(topic, []):
            await handler(evt.model_dump())

    async def replay_persistent(self, topic: str) -> None:
        if self._persistence is None:
            return
        for ts, payload in self._persistence.load(topic):
            evt = {
                "topic": topic,
                "timestamp_us": ts,
                "payload": payload,
                "source_service": "replay",
                "message_id": None,
                "persistence_tier": PersistenceTier.CRITICAL.value,
            }
            for handler in self._subscriptions.get(topic, []):
                await handler(evt)
