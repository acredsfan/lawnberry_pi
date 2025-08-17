"""
SQLite Database Manager
Persistent storage for configuration, maps, schedules, and historical data
"""

import asyncio
try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except Exception:
    aiosqlite = None
    AIOSQLITE_AVAILABLE = False

    # Minimal async stub to allow import and basic operations in tests where aiosqlite
    # is not installed. These implementations are no-ops and do not provide persistence.
    class _DummyCursor:
        async def execute(self, *args, **kwargs):
            return None

        async def fetchall(self):
            return []

        async def fetchone(self):
            return None

    class _DummyDB:
        def __init__(self, path=None):
            self._data = {}

        async def execute(self, *args, **kwargs):
            return _DummyCursor()

        async def commit(self):
            return None

        async def close(self):
            return None

        async def backup(self, other):
            return None

    async def connect(path):
        return _DummyDB(path)
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
from pathlib import Path

from .models import (
    SensorReading, NavigationData, OperationalState, PerformanceMetric,
    OperationalLog, ConfigurationData, DataType
)


class DatabaseManager:
    """SQLite-based persistent storage manager"""
    
    def __init__(self, db_path: str = "/var/lib/lawnberry/data.db"):
        self.logger = logging.getLogger(__name__)
        self.db_path = Path(db_path)
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connection pool
        self._connection_pool: Dict[str, aiosqlite.Connection] = {}
        self._pool_lock = asyncio.Lock()
        self._max_connections = 10
        
        # Performance settings
        self.batch_size = 1000
        self.vacuum_interval = timedelta(days=7)
        self.last_vacuum = None
        
        # Data retention policies (days)
        self.retention_policies = {
            'sensor_readings': 30,
            'navigation_data': 14,
            'operational_logs': 60,
            'performance_metrics': 90,
            'operational_states': 7
        }
        
        self._initialized = False
        self._schema_version = 1
    
    async def initialize(self) -> bool:
        """Initialize database with schema"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Enable WAL mode for better concurrency
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.execute("PRAGMA cache_size=10000")
                await db.execute("PRAGMA temp_store=MEMORY")
                
                # Create tables
                await self._create_tables(db)
                await self._create_indexes(db)
                
                # Set schema version
                await db.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    ("schema_version", str(self._schema_version))
                )
                
                await db.commit()
                
            self._initialized = True
            self.logger.info(f"Database initialized at {self.db_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            return False
    
    async def _create_tables(self, db: Any):
        """Create database tables"""
        
        # Metadata table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Sensor readings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT NOT NULL,
                sensor_type TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                value TEXT NOT NULL,
                unit TEXT DEFAULT '',
                quality REAL DEFAULT 1.0,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Navigation data
        await db.execute("""
            CREATE TABLE IF NOT EXISTS navigation_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                position TEXT NOT NULL,
                heading REAL NOT NULL,
                speed REAL NOT NULL,
                target_position TEXT,
                path_points TEXT DEFAULT '[]',
                obstacles TEXT DEFAULT '[]',
                coverage_map TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Operational states
        await db.execute("""
            CREATE TABLE IF NOT EXISTS operational_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT NOT NULL,
                mode TEXT NOT NULL,
                battery_level REAL NOT NULL,
                current_task TEXT,
                progress REAL DEFAULT 0.0,
                estimated_completion TIMESTAMP,
                last_update TIMESTAMP NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Performance metrics
        await db.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                value REAL NOT NULL,
                category TEXT NOT NULL,
                tags TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Operational logs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS operational_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                level TEXT NOT NULL,
                component TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT DEFAULT '{}',
                correlation_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Configuration data
        await db.execute("""
            CREATE TABLE IF NOT EXISTS configurations (
                config_id TEXT PRIMARY KEY,
                section TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                data_type TEXT NOT NULL,
                last_modified TIMESTAMP NOT NULL,
                version INTEGER DEFAULT 1,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Maps and boundaries
        await db.execute("""
            CREATE TABLE IF NOT EXISTS maps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                map_type TEXT NOT NULL,
                name TEXT NOT NULL,
                data TEXT NOT NULL,
                checksum TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Schedules
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                pattern TEXT NOT NULL,
                schedule_data TEXT NOT NULL,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    async def _create_indexes(self, db: Any):
        """Create database indexes for performance"""
        
        indexes = [
            # Sensor readings indexes
            "CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp ON sensor_readings(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_id ON sensor_readings(sensor_id)",
            "CREATE INDEX IF NOT EXISTS idx_sensor_readings_type ON sensor_readings(sensor_type)",
            
            # Navigation data indexes
            "CREATE INDEX IF NOT EXISTS idx_navigation_timestamp ON navigation_data(timestamp DESC)",
            
            # Performance metrics indexes
            "CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_performance_category ON performance_metrics(category)",
            "CREATE INDEX IF NOT EXISTS idx_performance_name ON performance_metrics(metric_name)",
            
            # Operational logs indexes
            "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON operational_logs(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_logs_level ON operational_logs(level)",
            "CREATE INDEX IF NOT EXISTS idx_logs_component ON operational_logs(component)",
            "CREATE INDEX IF NOT EXISTS idx_logs_correlation ON operational_logs(correlation_id)",
            
            # Configuration indexes
            "CREATE INDEX IF NOT EXISTS idx_config_section ON configurations(section)",
            "CREATE INDEX IF NOT EXISTS idx_config_key ON configurations(key)",
        ]
        
        for index_sql in indexes:
            await db.execute(index_sql)
    
    async def _get_connection(self) -> Any:
        """Get database connection from pool"""
        async with self._pool_lock:
            thread_id = str(asyncio.current_task())
            
            if thread_id not in self._connection_pool:
                if len(self._connection_pool) >= self._max_connections:
                    # Close oldest connection
                    oldest_key = next(iter(self._connection_pool))
                    await self._connection_pool[oldest_key].close()
                    del self._connection_pool[oldest_key]
                
                # Create new connection
                conn = await aiosqlite.connect(self.db_path)
                await conn.execute("PRAGMA journal_mode=WAL")
                self._connection_pool[thread_id] = conn
            
            return self._connection_pool[thread_id]
    
    async def store_sensor_reading(self, reading: SensorReading) -> bool:
        """Store sensor reading"""
        try:
            db = await self._get_connection()
            
            await db.execute("""
                INSERT INTO sensor_readings 
                (sensor_id, sensor_type, timestamp, value, unit, quality, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                reading.sensor_id,
                reading.sensor_type,
                reading.timestamp,
                json.dumps(reading.value, default=str),
                reading.unit,
                reading.quality,
                json.dumps(reading.metadata)
            ))
            
            await db.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing sensor reading: {e}")
            return False
    
    async def get_sensor_readings(self, sensor_id: str = None, 
                                 sensor_type: str = None,
                                 start_time: datetime = None,
                                 end_time: datetime = None,
                                 limit: int = 1000) -> List[SensorReading]:
        """Get sensor readings with filtering"""
        try:
            db = await self._get_connection()
            
            query = "SELECT * FROM sensor_readings WHERE 1=1"
            params = []
            
            if sensor_id:
                query += " AND sensor_id = ?"
                params.append(sensor_id)
            
            if sensor_type:
                query += " AND sensor_type = ?"
                params.append(sensor_type)
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                
                readings = []
                for row in rows:
                    reading = SensorReading(
                        sensor_id=row[1],
                        sensor_type=row[2],
                        timestamp=datetime.fromisoformat(row[3]),
                        value=json.loads(row[4]),
                        unit=row[5],
                        quality=row[6],
                        metadata=json.loads(row[7])
                    )
                    readings.append(reading)
                
                return readings
                
        except Exception as e:
            self.logger.error(f"Error getting sensor readings: {e}")
            return []
    
    async def store_navigation_data(self, nav_data: NavigationData) -> bool:
        """Store navigation data"""
        try:
            db = await self._get_connection()
            
            await db.execute("""
                INSERT INTO navigation_data 
                (timestamp, position, heading, speed, target_position, path_points, obstacles, coverage_map)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nav_data.timestamp,
                json.dumps(nav_data.position),
                nav_data.heading,
                nav_data.speed,
                json.dumps(nav_data.target_position) if nav_data.target_position else None,
                json.dumps(nav_data.path_points),
                json.dumps(nav_data.obstacles),
                json.dumps(nav_data.coverage_map) if nav_data.coverage_map else None
            ))
            
            await db.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing navigation data: {e}")
            return False
    
    async def store_operational_state(self, state: OperationalState) -> bool:
        """Store operational state"""
        try:
            db = await self._get_connection()
            
            await db.execute("""
                INSERT INTO operational_states 
                (state, mode, battery_level, current_task, progress, estimated_completion, last_update, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                state.state,
                state.mode,
                state.battery_level,
                state.current_task,
                state.progress,
                state.estimated_completion,
                state.last_update,
                json.dumps(state.metadata)
            ))
            
            await db.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing operational state: {e}")
            return False
    
    async def get_latest_operational_state(self) -> Optional[OperationalState]:
        """Get most recent operational state"""
        try:
            db = await self._get_connection()
            
            async with db.execute("""
                SELECT * FROM operational_states 
                ORDER BY last_update DESC LIMIT 1
            """) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return OperationalState(
                        state=row[1],
                        mode=row[2],
                        battery_level=row[3],
                        current_task=row[4],
                        progress=row[5],
                        estimated_completion=datetime.fromisoformat(row[6]) if row[6] else None,
                        last_update=datetime.fromisoformat(row[7]),
                        metadata=json.loads(row[8])
                    )
                
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting operational state: {e}")
            return None
    
    async def store_configuration(self, config: ConfigurationData) -> bool:
        """Store configuration data"""
        try:
            db = await self._get_connection()
            
            await db.execute("""
                INSERT OR REPLACE INTO configurations 
                (config_id, section, key, value, data_type, last_modified, version, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config.config_id,
                config.section,
                config.key,
                json.dumps(config.value, default=str),
                config.data_type,
                config.last_modified,
                config.version,
                json.dumps(config.metadata)
            ))
            
            await db.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing configuration: {e}")
            return False
    
    async def get_configurations(self, section: str = None) -> List[ConfigurationData]:
        """Get configuration data"""
        try:
            db = await self._get_connection()
            
            if section:
                query = "SELECT * FROM configurations WHERE section = ?"
                params = [section]
            else:
                query = "SELECT * FROM configurations"
                params = []
            
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                
                configs = []
                for row in rows:
                    config = ConfigurationData(
                        config_id=row[0],
                        section=row[1],
                        key=row[2],
                        value=json.loads(row[3]),
                        data_type=row[4],
                        last_modified=datetime.fromisoformat(row[5]),
                        version=row[6],
                        metadata=json.loads(row[7])
                    )
                    configs.append(config)
                
                return configs
                
        except Exception as e:
            self.logger.error(f"Error getting configurations: {e}")
            return []
    
    async def cleanup_old_data(self) -> Dict[str, int]:
        """Clean up old data based on retention policies"""
        cleanup_results = {}
        
        try:
            db = await self._get_connection()
            
            for table, retention_days in self.retention_policies.items():
                cutoff_date = datetime.now() - timedelta(days=retention_days)
                
                result = await db.execute(f"""
                    DELETE FROM {table} WHERE timestamp < ?
                """, (cutoff_date,))
                
                cleanup_results[table] = result.rowcount
                
            await db.commit()
            
            # Vacuum database if needed
            if not self.last_vacuum or datetime.now() - self.last_vacuum > self.vacuum_interval:
                await db.execute("VACUUM")
                self.last_vacuum = datetime.now()
                cleanup_results['vacuum'] = True
            
            total_cleaned = sum(cleanup_results.values())
            self.logger.info(f"Cleaned up {total_cleaned} old records")
            
            return cleanup_results
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            return {}
    
    async def backup_database(self, backup_path: str) -> bool:
        """Create database backup"""
        try:
            backup_db = await aiosqlite.connect(backup_path)
            db = await self._get_connection()
            
            await db.backup(backup_db)
            await backup_db.close()
            
            self.logger.info(f"Database backed up to {backup_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Database backup failed: {e}")
            return False
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics"""
        try:
            db = await self._get_connection()
            
            stats = {}
            
            # Table row counts
            tables = ['sensor_readings', 'navigation_data', 'operational_states', 
                     'performance_metrics', 'operational_logs', 'configurations']
            
            for table in tables:
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    count = await cursor.fetchone()
                    stats[f"{table}_count"] = count[0] if count else 0
            
            # Database size
            stats['database_size'] = os.path.getsize(self.db_path)
            
            # Schema version
            async with db.execute("SELECT value FROM metadata WHERE key = 'schema_version'") as cursor:
                version = await cursor.fetchone()
                stats['schema_version'] = version[0] if version else 'unknown'
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting database statistics: {e}")
            return {}
    
    async def close(self):
        """Close all database connections"""
        async with self._pool_lock:
            for conn in self._connection_pool.values():
                await conn.close()
            self._connection_pool.clear()
