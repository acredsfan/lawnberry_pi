# backend/src/repositories/mission_repository.py
"""MissionRepository: single owner of mission definition and execution state persistence."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import BaseRepository

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = ("completed", "aborted", "failed")


class MissionRepository(BaseRepository):
    """Owns all mission and execution-state persistence.

    Tables: `missions`, `mission_execution_state`.
    The existing PersistenceLayer SQL is migrated here verbatim so the
    production database schema is unchanged; only the caller changes.
    """

    _MIGRATIONS = [
        (
            1,
            """
            CREATE TABLE IF NOT EXISTS missions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                waypoints_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mission_execution_state (
                mission_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                current_waypoint_index INTEGER DEFAULT 0,
                completion_percentage REAL DEFAULT 0,
                total_waypoints INTEGER DEFAULT 0,
                detail TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mission_id) REFERENCES missions(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_mission_execution_status
                ON mission_execution_state(status);
            INSERT OR REPLACE INTO schema_version (version) VALUES (1);
            """,
        ),
    ]

    @property
    def _migrations(self) -> list[tuple[int, str]]:
        return self._MIGRATIONS

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self._apply_migrations()

    # ------------------------------------------------------------------
    # Missions
    # ------------------------------------------------------------------
    def save_mission(self, mission: dict[str, Any]) -> None:
        """Upsert a mission definition."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO missions (id, name, waypoints_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    mission["id"],
                    mission["name"],
                    json.dumps(mission.get("waypoints", [])),
                    mission.get("created_at", datetime.now(UTC).isoformat()),
                ),
            )
            conn.commit()

    def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        """Return mission dict or None."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            m = dict(row)
            m["waypoints"] = json.loads(m.pop("waypoints_json"))
            return m

    def list_missions(self) -> list[dict[str, Any]]:
        """Return all missions ordered by created_at."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM missions ORDER BY created_at")
            missions = []
            for row in cursor.fetchall():
                m = dict(row)
                m["waypoints"] = json.loads(m.pop("waypoints_json"))
                missions.append(m)
            return missions

    def delete_mission(self, mission_id: str) -> bool:
        """Delete mission and cascading execution state. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Execution state
    # ------------------------------------------------------------------
    def save_execution_state(self, state: dict[str, Any]) -> None:
        """Upsert execution state for a mission."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO mission_execution_state
                (mission_id, status, current_waypoint_index, completion_percentage,
                 total_waypoints, detail, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state["mission_id"],
                    state["status"],
                    state.get("current_waypoint_index", 0),
                    state.get("completion_percentage", 0.0),
                    state.get("total_waypoints", 0),
                    state.get("detail"),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()

    def get_execution_state(self, mission_id: str) -> dict[str, Any] | None:
        """Return execution state dict or None."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM mission_execution_state WHERE mission_id = ?", (mission_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_execution_states_by_status(self, status: str) -> list[dict[str, Any]]:
        """Return all execution states matching *status*."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM mission_execution_state WHERE status = ?", (status,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def prune_terminal_missions(self, retention_days: int = 30) -> int:
        """Delete terminal missions older than retention_days. Returns deleted count."""
        # Calculate cutoff ISO timestamp: everything older than this gets deleted
        cutoff_delta_seconds = retention_days * 86400
        cutoff_timestamp = datetime.now(UTC).timestamp() - cutoff_delta_seconds
        cutoff_iso = datetime.fromtimestamp(cutoff_timestamp, tz=UTC).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM missions
                WHERE id IN (
                    SELECT m.id FROM missions m
                    JOIN mission_execution_state mes ON m.id = mes.mission_id
                    WHERE mes.status IN ('completed', 'aborted', 'failed')
                      AND m.created_at < ?
                )
                """,
                (cutoff_iso,),
            )
            conn.commit()
            return cursor.rowcount
