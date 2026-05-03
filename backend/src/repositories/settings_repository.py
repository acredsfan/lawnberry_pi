# backend/src/repositories/settings_repository.py
"""SettingsRepository: single owner of operator settings and UI settings persistence.

Replaces the dual JSON-file + system_config SQLite write pattern in
SettingsService and routers/settings.py. The repository serialises settings
as a single JSON blob per logical key ('operator' and 'ui').
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import BaseRepository

logger = logging.getLogger(__name__)

_KEY_OPERATOR = "operator"
_KEY_UI = "ui"


class SettingsRepository(BaseRepository):
    """Owns operator settings and UI settings persistence.

    Storage: SQLite table `operator_settings` in the provided db_path.
    Two logical records are stored: key='operator' and key='ui'.
    """

    _MIGRATIONS = [
        (
            1,
            """
            CREATE TABLE IF NOT EXISTS operator_settings (
                key TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
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
    # Operator settings
    # ------------------------------------------------------------------
    def load(self) -> dict[str, Any] | None:
        """Return the operator settings dict, or None if not yet saved."""
        return self._load_key(_KEY_OPERATOR)

    def save(self, settings: dict[str, Any]) -> None:
        """Replace the entire operator settings record."""
        self._save_key(_KEY_OPERATOR, settings)
        logger.debug("SettingsRepository: saved operator settings (version=%s)", settings.get("version"))

    def patch(self, partial: dict[str, Any]) -> dict[str, Any]:
        """Merge *partial* into existing settings; create record if absent.

        Returns the resulting settings dict.
        """
        current = self.load() or {}
        current.update(partial)
        self.save(current)
        return current

    # ------------------------------------------------------------------
    # UI settings (maps section, dashboard preferences, etc.)
    # ------------------------------------------------------------------
    def load_ui_settings(self) -> dict[str, Any] | None:
        """Return the UI settings dict, or None if not yet saved."""
        return self._load_key(_KEY_UI)

    def save_ui_settings(self, ui_settings: dict[str, Any]) -> None:
        """Replace the entire UI settings record."""
        self._save_key(_KEY_UI, ui_settings)
        logger.debug("SettingsRepository: saved UI settings")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_key(self, key: str) -> dict[str, Any] | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT settings_json FROM operator_settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return json.loads(row["settings_json"])

    def _save_key(self, key: str, data: dict[str, Any]) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO operator_settings (key, settings_json, updated_at) "
                "VALUES (?, ?, ?)",
                (key, json.dumps(data), datetime.now(UTC).isoformat()),
            )
            conn.commit()
