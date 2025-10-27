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
    
    SCHEMA_VERSION = 4
    
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
            
            CREATE TABLE IF NOT EXISTS hardware_telemetry_streams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                component_id TEXT NOT NULL,
                value TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                stream_json TEXT NOT NULL,
                verification_artifact_id TEXT,
                UNIQUE(timestamp, component_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON hardware_telemetry_streams(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_telemetry_component ON hardware_telemetry_streams(component_id);
            
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
        ,
        Migration(
            version=2,
            description="Add audit_logs table",
            sql="""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                client_id TEXT,
                action TEXT NOT NULL,
                resource TEXT,
                details_json TEXT
            );

            INSERT OR REPLACE INTO schema_version (version) VALUES (2);
            """
        )
        ,
        Migration(
            version=3,
            description="Ensure telemetry streams table exists",
            sql="""
            CREATE TABLE IF NOT EXISTS hardware_telemetry_streams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                component_id TEXT NOT NULL,
                value TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms REAL NOT NULL,
                stream_json TEXT NOT NULL,
                verification_artifact_id TEXT,
                UNIQUE(timestamp, component_id)
            );
            CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON hardware_telemetry_streams(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_telemetry_component ON hardware_telemetry_streams(component_id);
            INSERT OR REPLACE INTO schema_version (version) VALUES (3);
            """
        )
        ,
        Migration(
            version=4,
            description="Add map_config table for map configuration storage",
            sql="""
            CREATE TABLE IF NOT EXISTS map_config (
                id TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT OR REPLACE INTO schema_version (version) VALUES (4);
            """
        )
    ]
    
    def __init__(self, db_path: str = "data/lawnberry.db"):
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
    
    # Map Configuration
    async def save_map_configuration(self, config_id: str, config_json: str) -> None:
        """Save map configuration to database."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO map_config (id, config_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (config_id, config_json, datetime.now(timezone.utc)),
            )
            conn.commit()
            logger.info(f"Saved map configuration {config_id} to persistence")
    
    async def load_map_configuration(self, config_id: str) -> Optional[str]:
        """Load map configuration from database."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT config_json FROM map_config WHERE id = ?",
                (config_id,),
            )
            result = cursor.fetchone()
            if result:
                logger.info(f"Loaded map configuration {config_id} from persistence")
                return result["config_json"]
            return None

    # Audit Logs
    def add_audit_log(self, action: str, client_id: Optional[str] = None, resource: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_logs (client_id, action, resource, details_json) VALUES (?, ?, ?, ?)",
                (client_id, action, resource, json.dumps(details or {}))
            )
            conn.commit()

    def load_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, client_id, action, resource, details_json FROM audit_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = []
            for r in cursor.fetchall():
                rows.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "client_id": r["client_id"],
                    "action": r["action"],
                    "resource": r["resource"],
                    "details": json.loads(r["details_json"]) if r["details_json"] else {}
                })
            return rows
    
    # Hardware Telemetry Streams
    def save_telemetry_streams(self, streams: List[Dict[str, Any]]) -> None:
        """Save hardware telemetry streams to database."""
        with self.get_connection() as conn:
            for stream in streams:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO hardware_telemetry_streams
                        (timestamp, component_id, value, status, latency_ms, stream_json, verification_artifact_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        stream.get("timestamp"),
                        stream.get("component_id"),
                        str(stream.get("value", "")),
                        stream.get("status"),
                        stream.get("latency_ms", 0.0),
                        json.dumps(stream),
                        stream.get("verification_artifact_id")
                    ))
                except Exception as e:
                    logger.error(f"Failed to save telemetry stream: {e}")
            conn.commit()
    
    def load_telemetry_streams(self, limit: int = 100, component_id: Optional[str] = None,
                               start_time: Optional[str] = None, end_time: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load hardware telemetry streams from database with optional filters."""
        with self.get_connection() as conn:
            query = "SELECT * FROM hardware_telemetry_streams WHERE 1=1"
            params = []
            
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
            
            cursor = conn.execute(query, params)
            streams = []
            for row in cursor.fetchall():
                stream = json.loads(row["stream_json"])
                stream["db_id"] = row["id"]
                streams.append(stream)
            return streams
    
    def compute_telemetry_latency_stats(self, component_id: Optional[str] = None,
                                       start_time: Optional[str] = None,
                                       end_time: Optional[str] = None) -> Dict[str, Any]:
        """Compute latency statistics for telemetry streams."""
        with self.get_connection() as conn:
            query = """
                SELECT 
                    COUNT(*) as count,
                    AVG(latency_ms) as avg_latency,
                    MIN(latency_ms) as min_latency,
                    MAX(latency_ms) as max_latency,
                    component_id
                FROM hardware_telemetry_streams
                WHERE 1=1
            """
            params = []
            
            if component_id:
                query += " AND component_id = ?"
                params.append(component_id)
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            if not component_id:
                query += " GROUP BY component_id"
            
            cursor = conn.execute(query, params)
            
            if component_id:
                row = cursor.fetchone()
                if row:
                    return {
                        "component_id": component_id,
                        "count": row["count"],
                        "avg_latency_ms": row["avg_latency"],
                        "min_latency_ms": row["min_latency"],
                        "max_latency_ms": row["max_latency"]
                    }
                return {}
            else:
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "component_id": row["component_id"],
                        "count": row["count"],
                        "avg_latency_ms": row["avg_latency"],
                        "min_latency_ms": row["min_latency"],
                        "max_latency_ms": row["max_latency"]
                    })
                return {"by_component": results}
    
    def cleanup_old_telemetry_streams(self, days_to_keep: int = 7) -> int:
        """Clean up old telemetry stream data to manage disk space."""
        cutoff = datetime.now(timezone.utc).timestamp() - (days_to_keep * 24 * 3600)
        with self.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM hardware_telemetry_streams WHERE timestamp < datetime(?, 'unixepoch')",
                (cutoff,)
            )
            conn.commit()
            return cursor.rowcount
    
    def export_telemetry_diagnostic(self, component_id: Optional[str] = None,
                                   start_time: Optional[str] = None,
                                   end_time: Optional[str] = None) -> Dict[str, Any]:
        """Export telemetry diagnostic data including power metrics and status."""
        streams = self.load_telemetry_streams(
            limit=1000,
            component_id=component_id,
            start_time=start_time,
            end_time=end_time
        )
        
        stats = self.compute_telemetry_latency_stats(
            component_id=component_id,
            start_time=start_time,
            end_time=end_time
        )
        
        return {
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "filters": {
                "component_id": component_id,
                "start_time": start_time,
                "end_time": end_time
            },
            "statistics": stats,
            "stream_count": len(streams),
            "streams": streams
        }

    # Test helper: seed minimal simulated streams when SIM_MODE enabled
    def seed_simulated_streams(self, count: int = 10) -> None:
        import os
        if os.environ.get("SIM_MODE") != "1":
            return
        now = datetime.now(timezone.utc)
        rows = []
        for i in range(count):
            ts = (now).isoformat()
            rows.append({
                "timestamp": ts,
                "component_id": "power",
                "value": {"voltage": 12.5, "percentage": 80},
                "status": "healthy",
                "latency_ms": 0.0,
            })
        try:
            self.save_telemetry_streams(rows)
        except Exception:
            pass


# Global persistence instance
persistence = PersistenceLayer()