"""EventStore — persistence filter and writer for structured domain events."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from .events import DomainEvent, PersistenceMode, SUMMARY_MODE_EVENTS

logger = logging.getLogger(__name__)


class EventStore:
    """Filters and persists domain events based on the active persistence mode.

    Args:
        persistence: A PersistenceLayer instance. Pass None to disable all writes.
        mode: PersistenceMode.FULL or PersistenceMode.SUMMARY.
    """

    def __init__(self, persistence: Any, mode: PersistenceMode) -> None:
        self._persistence = persistence
        self._mode = mode

    @property
    def mode(self) -> PersistenceMode:
        return self._mode

    def emit(self, event: DomainEvent) -> None:
        """Persist the event if the current mode allows it.

        Failures are logged as warnings; they never propagate to the caller.
        """
        if self._persistence is None:
            return
        if self._mode == PersistenceMode.SUMMARY:
            if event.event_type not in SUMMARY_MODE_EVENTS:
                return
        try:
            self._write(event)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to persist event %s: %s", event.event_type, exc)

    def _write(self, event: DomainEvent) -> None:
        payload = asdict(event)
        timestamp = payload.pop("timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        run_id = payload.pop("run_id", "")
        mission_id = payload.pop("mission_id", "")
        event_type = payload.pop("event_type", event.event_type)

        with self._persistence.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO mission_events
                    (run_id, mission_id, event_type, payload_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, mission_id, event_type, json.dumps(payload), timestamp),
            )
            conn.commit()

    def load_events(
        self,
        run_id: str,
        event_type: str | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Return stored events for a run, optionally filtered by event_type."""
        if self._persistence is None:
            return []
        with self._persistence.get_connection() as conn:
            if event_type:
                cursor = conn.execute(
                    """
                    SELECT run_id, mission_id, event_type, payload_json, timestamp
                    FROM mission_events
                    WHERE run_id = ? AND event_type = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (run_id, event_type, limit),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT run_id, mission_id, event_type, payload_json, timestamp
                    FROM mission_events
                    WHERE run_id = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (run_id, limit),
                )
            rows = []
            for row in cursor.fetchall():
                payload = json.loads(row["payload_json"])
                payload["run_id"] = row["run_id"]
                payload["mission_id"] = row["mission_id"]
                payload["event_type"] = row["event_type"]
                payload["timestamp"] = row["timestamp"]
                rows.append(payload)
            return rows
