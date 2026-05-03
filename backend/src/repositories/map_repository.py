# backend/src/repositories/map_repository.py
"""MapRepository: single owner of zone and map-configuration persistence."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import BaseRepository

logger = logging.getLogger(__name__)


class MapRepository(BaseRepository):
    """Owns all map zone and map configuration persistence.

    Storage: SQLite tables `map_zones` and `map_config` in the provided db_path.
    Callers never write SQL; they call typed methods.
    """

    _MIGRATIONS = [
        (
            1,
            """
            CREATE TABLE IF NOT EXISTS map_zones (
                id TEXT PRIMARY KEY,
                name TEXT,
                polygon_json TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                exclusion_zone BOOLEAN DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS map_config (
                id TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
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
    # Zones
    # ------------------------------------------------------------------
    def save_zones(self, zones: list[dict[str, Any]]) -> None:
        """Replace all stored zones atomically."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM map_zones")
            for zone in zones:
                conn.execute(
                    "INSERT INTO map_zones (id, name, polygon_json, priority, exclusion_zone) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        zone["id"],
                        zone.get("name"),
                        json.dumps(zone["polygon"]),
                        zone.get("priority", 0),
                        int(bool(zone.get("exclusion_zone", False))),
                    ),
                )
            conn.commit()

    def list_zones(self) -> list[dict[str, Any]]:
        """Return all zones ordered by descending priority."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM map_zones ORDER BY priority DESC")
            zones = []
            for row in cursor.fetchall():
                z = dict(row)
                z["polygon"] = json.loads(z.pop("polygon_json"))
                zones.append(z)
            return zones

    def delete_zone(self, zone_id: str) -> bool:
        """Delete a single zone by id. Returns True if a row was deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM map_zones WHERE id = ?", (zone_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Map configuration
    # ------------------------------------------------------------------
    def save_map_config(self, config_id: str, config: dict[str, Any]) -> None:
        """Upsert a map configuration blob."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO map_config (id, config_json, updated_at) VALUES (?, ?, ?)",
                (config_id, json.dumps(config), datetime.now(UTC).isoformat()),
            )
            conn.commit()
        logger.debug("MapRepository: saved map config %s", config_id)

    def load_map_config(self, config_id: str) -> dict[str, Any] | None:
        """Return the config dict or None if not found."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT config_json FROM map_config WHERE id = ?", (config_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return json.loads(row["config_json"])
