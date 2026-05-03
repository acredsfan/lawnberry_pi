"""TelemetryRepository: single owner of snapshot and hardware stream persistence.

Enforces TTL-based retention as a first-class method (cleanup_snapshots,
cleanup_streams) instead of leaving retention ad hoc to callers.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .base import BaseRepository

logger = logging.getLogger(__name__)


class TelemetryRepository(BaseRepository):
    """Owns telemetry snapshot and hardware stream persistence."""

    _MIGRATIONS = [
        (
            1,
            """
            CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hardware_telemetry_streams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                component_id TEXT NOT NULL,
                value TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                stream_json TEXT NOT NULL,
                verification_artifact_id TEXT,
                UNIQUE(timestamp, component_id)
            );
            CREATE INDEX IF NOT EXISTS idx_tel_ts ON hardware_telemetry_streams(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_tel_comp ON hardware_telemetry_streams(component_id);
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
    # Snapshots
    # ------------------------------------------------------------------
    def save_snapshot(self, data: dict[str, Any]) -> None:
        """Append a telemetry snapshot."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO telemetry_snapshots (timestamp, data_json) VALUES (?, ?)",
                (datetime.now(UTC).isoformat(), json.dumps(data)),
            )
            conn.commit()

    def list_snapshots(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent *limit* snapshots, newest first."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, data_json FROM telemetry_snapshots "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            results = []
            for row in cursor.fetchall():
                results.append(
                    {
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "data": json.loads(row["data_json"]),
                    }
                )
            return results

    def cleanup_snapshots(self, days_to_keep: int = 7) -> int:
        """Delete snapshots older than *days_to_keep*. Returns deleted count."""
        cutoff_time = datetime.now(UTC) - timedelta(days=days_to_keep)
        cutoff_iso = cutoff_time.isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM telemetry_snapshots WHERE timestamp < ?",
                (cutoff_iso,),
            )
            conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Hardware telemetry streams
    # ------------------------------------------------------------------
    def save_streams(self, streams: list[dict[str, Any]]) -> None:
        """Upsert a list of hardware telemetry stream records."""
        with self._get_connection() as conn:
            for stream in streams:
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO hardware_telemetry_streams
                        (timestamp, component_id, value, status, latency_ms,
                         stream_json, verification_artifact_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            stream.get("timestamp", datetime.now(UTC).isoformat()),
                            stream["component_id"],
                            json.dumps(stream.get("value", "")),
                            stream.get("status", "unknown"),
                            stream.get("latency_ms", 0.0),
                            json.dumps(stream),
                            stream.get("verification_artifact_id"),
                        ),
                    )
                except Exception as exc:
                    logger.error("TelemetryRepository: failed to save stream: %s", exc)
            conn.commit()

    def list_streams(
        self,
        limit: int = 100,
        component_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return hardware stream records with optional filters."""
        query = "SELECT * FROM hardware_telemetry_streams WHERE 1=1"
        params: list[Any] = []
        if component_id:
            query += " AND component_id = ?"
            params.append(component_id)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [json.loads(r["stream_json"]) for r in cursor.fetchall()]

    def compute_latency_stats(
        self,
        component_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """Compute latency statistics. Returns dict with count/avg/min/max."""
        query = """
            SELECT COUNT(*) as count, AVG(latency_ms) as avg_latency,
                   MIN(latency_ms) as min_latency, MAX(latency_ms) as max_latency
            FROM hardware_telemetry_streams WHERE 1=1
        """
        params: list[Any] = []
        if component_id:
            query += " AND component_id = ?"
            params.append(component_id)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if row is None or row["count"] == 0:
                return {"count": 0, "avg_latency_ms": None, "min_latency_ms": None, "max_latency_ms": None}
            return {
                "component_id": component_id,
                "count": row["count"],
                "avg_latency_ms": row["avg_latency"],
                "min_latency_ms": row["min_latency"],
                "max_latency_ms": row["max_latency"],
            }

    def cleanup_streams(self, days_to_keep: int = 7) -> int:
        """Delete stream records older than *days_to_keep*. Returns deleted count."""
        cutoff_time = datetime.now(UTC) - timedelta(days=days_to_keep)
        cutoff_iso = cutoff_time.isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM hardware_telemetry_streams WHERE timestamp < ?",
                (cutoff_iso,),
            )
            conn.commit()
            return cursor.rowcount
