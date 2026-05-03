"""Abstract base for all SQLite-backed repositories.

Provides a minimal shared interface:
- db_path: resolved Path to the SQLite file
- _get_connection(): context manager yielding a sqlite3.Connection
- _apply_migrations(): runs a list of (version, sql) tuples against schema_version
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseRepository(ABC):
    """SQLite-backed repository base class.

    Subclasses must implement `_migrations` (list of (version, sql) pairs) and
    call `self._apply_migrations()` from their `__init__` after setting `self.db_path`.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    @abstractmethod
    def _migrations(self) -> list[tuple[int, str]]:
        """Ordered list of (schema_version, sql_script) to apply in sequence."""

    def _apply_migrations(self) -> None:
        """Create schema_version table if absent; apply pending migrations."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.commit()
            cursor = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
            current: int = cursor.fetchone()[0]
            for version, sql in self._migrations:
                if version > current:
                    logger.info(
                        "%s: applying migration v%d", self.__class__.__name__, version
                    )
                    conn.executescript(sql)
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,)
                    )
                    conn.commit()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a sqlite3.Connection; serialises with a threading.Lock."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with self._lock:
                yield conn
        finally:
            conn.close()
