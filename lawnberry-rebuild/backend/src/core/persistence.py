"""SQLite persistence layer and database migrations.

This module provides a lightweight persistence layer for the LawnBerry Pi v2 system,
handling database schema creation, migrations, and basic CRUD operations for
persistent data like job schedules, configuration, and telemetry history.
"""
import sqlite3
import json
import logging
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Generator
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """Database migration definition."""
    version: int
    description: str
    sql: str


class PersistenceLayer:
    """SQLite-based persistence layer for LawnBerry Pi v2."""
    
    SCHEMA_VERSION = 1
    
    MIGRATIONS = [
        Migration(
            version=1,
            description="Initial schema",
            sql="""
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY,
                config_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS planning_jobs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                schedule TEXT NOT NULL,
                zones_json TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run TIMESTAMP,
                status TEXT DEFAULT 'pending'
            );
            
            CREATE TABLE IF NOT EXISTS telemetry_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_json TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS map_zones (
                id TEXT PRIMARY KEY,
                name TEXT,
                polygon_json TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                exclusion_zone BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Insert initial schema version
            INSERT OR REPLACE INTO schema_version (version) VALUES (1);
            """
        )
    ]
    
    def __init__(self, db_path: str = "/home/pi/lawnberry/data/lawnberry.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize database and run migrations."""
        with self.get_connection() as conn:
            # Get current schema version
            current_version = self._get_schema_version(conn)
            
            # Apply migrations
            for migration in self.MIGRATIONS:
                if migration.version > current_version:
                    logger.info(f"Applying migration {migration.version}: {migration.description}")
                    conn.executescript(migration.sql)
                    conn.commit()
    
    def _get_schema_version(self, conn: sqlite3.Connection) -> int:
        """Get current database schema version."""
        try:
            cursor = conn.execute("SELECT MAX(version) FROM schema_version")
            result = cursor.fetchone()
            return result[0] if result and result[0] is not None else 0
        except sqlite3.OperationalError:
            return 0
    
    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    # System Configuration
    def save_system_config(self, config: Dict[str, Any]) -> None:
        """Save system configuration to database."""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_config (id, config_json, updated_at) VALUES (1, ?, ?)",
                (json.dumps(config), datetime.now(timezone.utc))
            )
            conn.commit()
    
    def load_system_config(self) -> Optional[Dict[str, Any]]:
        """Load system configuration from database."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT config_json FROM system_config WHERE id = 1")
            result = cursor.fetchone()
            if result:
                return json.loads(result["config_json"])
            return None
    
    # Planning Jobs
    def save_planning_job(self, job_data: Dict[str, Any]) -> None:
        """Save planning job to database."""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO planning_jobs 
                (id, name, schedule, zones_json, priority, enabled, created_at, last_run, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_data["id"],
                job_data["name"],
                job_data["schedule"],
                json.dumps(job_data["zones"]),
                job_data.get("priority", 1),
                job_data.get("enabled", True),
                job_data.get("created_at"),
                job_data.get("last_run"),
                job_data.get("status", "pending")
            ))
            conn.commit()
    
    def load_planning_jobs(self) -> List[Dict[str, Any]]:
        """Load all planning jobs from database."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM planning_jobs ORDER BY created_at")
            jobs = []
            for row in cursor.fetchall():
                job = dict(row)
                job["zones"] = json.loads(job["zones_json"])
                del job["zones_json"]
                jobs.append(job)
            return jobs
    
    def delete_planning_job(self, job_id: str) -> bool:
        """Delete planning job from database."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM planning_jobs WHERE id = ?", (job_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    # Map Zones
    def save_map_zones(self, zones: List[Dict[str, Any]]) -> None:
        """Save map zones to database."""
        with self.get_connection() as conn:
            # Clear existing zones
            conn.execute("DELETE FROM map_zones")
            
            # Insert new zones
            for zone in zones:
                conn.execute("""
                    INSERT INTO map_zones (id, name, polygon_json, priority, exclusion_zone)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    zone["id"],
                    zone.get("name"),
                    json.dumps(zone["polygon"]),
                    zone.get("priority", 0),
                    zone.get("exclusion_zone", False)
                ))
            conn.commit()
    
    def load_map_zones(self) -> List[Dict[str, Any]]:
        """Load map zones from database."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM map_zones ORDER BY priority DESC")
            zones = []
            for row in cursor.fetchall():
                zone = dict(row)
                zone["polygon"] = json.loads(zone["polygon_json"])
                del zone["polygon_json"]
                zones.append(zone)
            return zones
    
    # Telemetry History
    def save_telemetry_snapshot(self, data: Dict[str, Any]) -> None:
        """Save telemetry snapshot for historical analysis."""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO telemetry_snapshots (timestamp, data_json) VALUES (?, ?)",
                (datetime.now(timezone.utc), json.dumps(data))
            )
            conn.commit()
    
    def load_telemetry_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Load recent telemetry history."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM telemetry_snapshots ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )
            snapshots = []
            for row in cursor.fetchall():
                snapshot = {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "data": json.loads(row["data_json"])
                }
                snapshots.append(snapshot)
            return snapshots
    
    def cleanup_old_telemetry(self, days_to_keep: int = 7) -> int:
        """Clean up old telemetry data to manage disk space."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days_to_keep * 24 * 3600)
        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM telemetry_snapshots WHERE timestamp < datetime(?, 'unixepoch')",
                (cutoff,)
            )
            conn.commit()
            return cursor.rowcount


# Global persistence instance
persistence = PersistenceLayer()