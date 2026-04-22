"""Tests for SQLite WAL mode and thread safety in DatabasePersistence."""
import sqlite3
import tempfile
import pathlib


def test_wal_mode_enabled_after_init():
    """Database must use WAL journal mode after initialization."""
    from backend.src.core.persistence import PersistenceLayer

    with tempfile.TemporaryDirectory() as tmp:
        db_path = pathlib.Path(tmp) / "test.db"
        persistence = PersistenceLayer(db_path=str(db_path))
        with persistence.get_connection() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0] == "wal", f"Expected WAL, got {row[0]}"
