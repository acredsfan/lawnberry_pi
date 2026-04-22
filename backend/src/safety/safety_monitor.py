from __future__ import annotations

"""Safety monitor and notification bridge (T121).

Collects safety interlock changes and watchdog/estop events and forwards them
to observability + WebSocket topics. This module has no direct hardware control.
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from ..core.observability import observability
from ..models.safety_interlock import SafetyInterlock


@dataclass
class SafetyEvent:
    timestamp: str
    action: str  # "activate" | "clear"
    interlock: dict[str, Any]


class SafetyMonitor:
    def __init__(self, websocket_hub: Any = None) -> None:
        self._events: list[SafetyEvent] = []
        self._lock = asyncio.Lock()
        self._websocket_hub = websocket_hub

    def set_websocket_hub(self, hub: Any) -> None:
        """Inject or replace the WebSocket hub after construction."""
        self._websocket_hub = hub

    async def handle_interlock_event(self, action: str, interlock: SafetyInterlock) -> None:
        evt = SafetyEvent(
            timestamp=datetime.now(UTC).isoformat(),
            action=action,
            interlock=interlock.model_dump(),
        )
        async with self._lock:
            self._events.append(evt)
            self._events = self._events[-100:]

        # Log and broadcast
        observability.record_event(
            event_type="safety",
            level="INFO",
            message=f"Interlock {action}: {interlock.interlock_type}",
            origin="safety.monitor",
            metadata={"action": action, "interlock": interlock.model_dump()},
        )
        if self._websocket_hub is not None:
            try:
                await self._websocket_hub.broadcast_to_topic(
                    "system.safety",
                    {
                        "action": action,
                        "interlock": interlock.model_dump(),
                        "timestamp": evt.timestamp,
                    },
                )
            except Exception:
                # Best-effort broadcast
                pass

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "recent_events": [asdict(e) for e in self._events],
            }


_monitor: SafetyMonitor | None = None


def get_safety_monitor() -> SafetyMonitor:
    global _monitor
    if _monitor is None:
        _monitor = SafetyMonitor()
    return _monitor


__all__ = ["SafetyMonitor", "get_safety_monitor"]
