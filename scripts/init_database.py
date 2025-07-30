#!/usr/bin/env python3
"""
Database Initialization Script
Sets up initial database schema and default configurations for LawnBerry Pi
"""

import os
import sys
import sqlite3
import json
import redis
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
import aiosqlite

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from data_management.database_manager import DatabaseManager
    from data_management.config import DataManagementConfig
except ImportError:
    DatabaseManager = None
    DataManagementConfig = None


class DatabaseInitializer:
    """Initializes database schema and default data"""
    
    def __init__(self, data_dir: str = "/var/lib/lawnberry"):
        self.data_dir = Path(data_dir)
        self.db_dir = self.data_dir / "database"
        self.sqlite_path = self.db_dir / "lawnberry.db"
        self.logger = self._setup_logging()
        
        # Ensure directories exist
        self.db_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for database initialization"""
        logger = logging.getLogger('db_initializer')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def initialize_sqlite(self) -> bool:
        """Initialize SQLite database with schema"""
        self.logger.info("Initializing SQLite database...")
        
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                cursor = conn.cursor()
                
                # Create tables
                self._create_system_tables(cursor)
                self._create_sensor_tables(cursor)
                self._create_weather_tables(cursor)
                self._create_navigation_tables(cursor)
                self._create_maintenance_tables(cursor)
                self._create_user_tables(cursor)
                
                # Insert default data
                self._insert_default_data(cursor)
                
                conn.commit()
            
            # Set proper permissions
            os.chmod(self.sqlite_path, 0o664)
            self.logger.info(f"SQLite database initialized: {self.sqlite_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize SQLite database: {e}")
            return False
    
    def _create_system_tables(self, cursor: sqlite3.Cursor):
        """Create system-related tables"""
        
        # System configuration table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                description TEXT,
                category TEXT DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # System health metrics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cpu_usage REAL,
                memory_usage REAL,
                disk_usage REAL,
                temperature REAL,
                services_status TEXT,
                hardware_status TEXT
            )
        ''')
        
        # System logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                level TEXT NOT NULL,
                component TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT
            )
        ''')
    
    def _create_sensor_tables(self, cursor: sqlite3.Cursor):
        """Create sensor data tables"""
        
        # Sensor readings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sensor_type TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                reading_type TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                quality_score REAL DEFAULT 1.0
            )
        ''')
        
        # Sensor calibration data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT UNIQUE NOT NULL,
                calibration_data TEXT NOT NULL,
                calibrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                calibrated_by TEXT DEFAULT 'system'
            )
        ''')
        
        # Hardware status
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hardware_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                device_type TEXT NOT NULL,
                device_id TEXT NOT NULL,
                status TEXT NOT NULL,
                health_score REAL DEFAULT 1.0,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_count INTEGER DEFAULT 0
            )
        ''')
    
    def _create_weather_tables(self, cursor: sqlite3.Cursor):
        """Create weather-related tables"""
        
        # Weather data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                temperature REAL,
                humidity REAL,
                pressure REAL,
                wind_speed REAL,
                wind_direction REAL,
                precipitation REAL,
                conditions TEXT,
                visibility REAL,
                uv_index REAL
            )
        ''')
        
        # Weather forecasts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forecast_time TIMESTAMP NOT NULL,
                retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                temperature_high REAL,
                temperature_low REAL,
                humidity REAL,
                precipitation_chance REAL,
                precipitation_amount REAL,
                wind_speed REAL,
                conditions TEXT
            )
        ''')
        
        # Weather alerts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weather_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                severity TEXT NOT NULL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                acknowledged_at TIMESTAMP
            )
        ''')
    
    def _create_navigation_tables(self, cursor: sqlite3.Cursor):
        """Create navigation and mapping tables"""
        
        # Yard boundaries
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS yard_boundaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                boundary_type TEXT DEFAULT 'main',
                coordinates TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        ''')
        
        # Mowing patterns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mowing_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                coordinates TEXT NOT NULL,
                parameters TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP
            )
        ''')
        
        # Navigation waypoints
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS navigation_waypoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                waypoint_type TEXT DEFAULT 'custom',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # GPS tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gps_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                altitude REAL,
                speed REAL,
                heading REAL,
                accuracy REAL,
                satellites INTEGER
            )
        ''')
    
    def _create_maintenance_tables(self, cursor: sqlite3.Cursor):
        """Create maintenance and operation tables"""
        
        # Mowing sessions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mowing_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                duration INTEGER,
                area_covered REAL,
                pattern_used TEXT,
                battery_start REAL,
                battery_end REAL,
                status TEXT DEFAULT 'completed',
                notes TEXT
            )
        ''')
        
        # Maintenance records
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS maintenance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maintenance_type TEXT NOT NULL,
                component TEXT NOT NULL,
                performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                performed_by TEXT DEFAULT 'system',
                next_due_date DATE,
                cost REAL,
                parts_used TEXT
            )
        ''')
        
        # Error logs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_type TEXT NOT NULL,
                component TEXT NOT NULL,
                error_code TEXT,
                message TEXT NOT NULL,
                stack_trace TEXT,
                resolved INTEGER DEFAULT 0,
                resolved_at TIMESTAMP
            )
        ''')
    
    def _create_user_tables(self, cursor: sqlite3.Cursor):
        """Create user and settings tables"""
        
        # User accounts
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        ''')
        
        # User preferences
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, preference_key)
            )
        ''')
        
        # Schedules
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                schedule_type TEXT DEFAULT 'mowing',
                cron_expression TEXT NOT NULL,
                parameters TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_run TIMESTAMP,
                next_run TIMESTAMP
            )
        ''')
    
    def _insert_default_data(self, cursor: sqlite3.Cursor):
        """Insert default configuration data"""
        
        default_configs = [
            ('system_name', 'LawnBerry Pi', 'System display name', 'system'),
            ('timezone', 'UTC', 'System timezone', 'system'),
            ('units_temperature', 'celsius', 'Temperature units', 'display'),
            ('units_distance', 'metric', 'Distance units', 'display'),
            ('units_speed', 'kmh', 'Speed units', 'display'),
            ('mowing_height', '3.0', 'Default mowing height (cm)', 'mowing'),
            ('mowing_speed', '0.5', 'Default mowing speed (m/s)', 'mowing'),
            ('safety_timeout', '30', 'Safety system timeout (seconds)', 'safety'),
            ('weather_check_interval', '300', 'Weather check interval (seconds)', 'weather'),
            ('gps_update_interval', '1', 'GPS update interval (seconds)', 'navigation'),
            ('battery_low_threshold', '20', 'Low battery threshold (%)', 'power'),
            ('battery_critical_threshold', '10', 'Critical battery threshold (%)', 'power'),
        ]
        
        for key, value, description, category in default_configs:
            cursor.execute('''
                INSERT OR IGNORE INTO system_config (key, value, description, category)
                VALUES (?, ?, ?, ?)
            ''', (key, value, description, category))
        
        # Default admin user (password: admin123)
        import hashlib
        password_hash = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        ''', ('admin', password_hash, 'admin'))
        
        # Default schedule (daily at 9 AM)
        cursor.execute('''
            INSERT OR IGNORE INTO schedules (name, schedule_type, cron_expression, parameters)
            VALUES (?, ?, ?, ?)
        ''', ('Daily Morning Mow', 'mowing', '0 9 * * *', '{"pattern": "default", "duration": 3600}'))
    
    def initialize_redis(self) -> bool:
        """Initialize Redis database"""
        self.logger.info("Initializing Redis database...")
        
        try:
            # Connect to Redis
            r = redis.Redis(host='localhost', port=6379, decode_responses=True)
            
            # Test connection
            r.ping()
            
            # Set up default cache keys
            default_cache = {
                'system:status': 'initializing',
                'system:last_health_check': '0',
                'weather:last_update': '0',
                'navigation:current_position': '{"lat": 0.0, "lon": 0.0}',
                'hardware:last_scan': '0',
            }
            
            for key, value in default_cache.items():
                r.setex(key, 3600, value)  # 1 hour expiry
            
            self.logger.info("Redis database initialized")
            return True
            
        except redis.ConnectionError:
            self.logger.warning("Redis not available - skipping Redis initialization")
            return False
        except Exception as e:
            self.logger.error(f"Failed to initialize Redis: {e}")
            return False
    
    def create_indexes(self) -> bool:
        """Create database indexes for performance"""
        self.logger.info("Creating database indexes...")
        
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                cursor = conn.cursor()
                
                # Indexes for performance
                indexes = [
                    'CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp ON sensor_readings(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor ON sensor_readings(sensor_type, sensor_id)',
                    'CREATE INDEX IF NOT EXISTS idx_weather_data_timestamp ON weather_data(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_gps_tracking_timestamp ON gps_tracking(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_system_health_timestamp ON system_health(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_error_logs_timestamp ON error_logs(timestamp)',
                    'CREATE INDEX IF NOT EXISTS idx_mowing_sessions_start_time ON mowing_sessions(start_time)',
                    'CREATE INDEX IF NOT EXISTS idx_system_config_key ON system_config(key)',
                    'CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)',
                ]
                
                for index_sql in indexes:
                    cursor.execute(index_sql)
                
                conn.commit()
            
            self.logger.info("Database indexes created")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create indexes: {e}")
            return False
    
    def setup_triggers(self) -> bool:
        """Set up database triggers"""
        self.logger.info("Setting up database triggers...")
        
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                cursor = conn.cursor()
                
                # Update timestamp trigger for system_config
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS update_system_config_timestamp 
                    AFTER UPDATE ON system_config
                    BEGIN
                        UPDATE system_config SET updated_at = CURRENT_TIMESTAMP 
                        WHERE id = NEW.id;
                    END
                ''')
                
                # Auto-cleanup old sensor readings (keep last 30 days)
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS cleanup_old_sensor_readings
                    AFTER INSERT ON sensor_readings
                    BEGIN
                        DELETE FROM sensor_readings 
                        WHERE timestamp < datetime('now', '-30 days');
                    END
                ''')
                
                # Auto-cleanup old GPS tracking (keep last 7 days)
                cursor.execute('''
                    CREATE TRIGGER IF NOT EXISTS cleanup_old_gps_tracking
                    AFTER INSERT ON gps_tracking
                    BEGIN
                        DELETE FROM gps_tracking 
                        WHERE timestamp < datetime('now', '-7 days');
                    END
                ''')
                
                conn.commit()
            
            self.logger.info("Database triggers created")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to create triggers: {e}")
            return False
    
    def run_full_initialization(self) -> bool:
        """Run complete database initialization"""
        self.logger.info("Starting complete database initialization...")
        
        success = True
        
        # Initialize SQLite
        if not self.initialize_sqlite():
            success = False
        
        # Create indexes
        if not self.create_indexes():
            success = False
        
        # Setup triggers
        if not self.setup_triggers():
            success = False
        
        # Initialize Redis
        if not self.initialize_redis():
            # Redis failure is not critical
            pass
        
        if success:
            self.logger.info("Database initialization completed successfully")
        else:
            self.logger.error("Database initialization completed with errors")
        
        return success
    
    def check_database_health(self) -> Dict[str, Any]:
        """Check database health and return status"""
        health = {
            'sqlite': {'available': False, 'tables': 0, 'records': 0},
            'redis': {'available': False, 'keys': 0}
        }
        
        # Check SQLite
        try:
            with sqlite3.connect(self.sqlite_path) as conn:
                cursor = conn.cursor()
                
                # Count tables
                cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                health['sqlite']['tables'] = cursor.fetchone()[0]
                
                # Count total records
                cursor.execute("SELECT COUNT(*) FROM system_config")
                health['sqlite']['records'] = cursor.fetchone()[0]
                
                health['sqlite']['available'] = True
                
        except Exception as e:
            health['sqlite']['error'] = str(e)
        
        # Check Redis
        try:
            r = redis.Redis(host='localhost', port=6379, decode_responses=True)
            r.ping()
            
            # Count keys
            health['redis']['keys'] = r.dbsize()
            health['redis']['available'] = True
            
        except Exception as e:
            health['redis']['error'] = str(e)
        
        return health


def main():
    """Main initialization function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='LawnBerry Pi Database Initialization')
    parser.add_argument('--data-dir', default='/var/lib/lawnberry',
                       help='Data directory path')
    parser.add_argument('--check-health', action='store_true',
                       help='Check database health instead of initializing')
    
    args = parser.parse_args()
    
    initializer = DatabaseInitializer(args.data_dir)
    
    if args.check_health:
        health = initializer.check_database_health()
        print("Database Health Status:")
        print(f"SQLite: {'✓' if health['sqlite']['available'] else '✗'} "
              f"({health['sqlite']['tables']} tables, {health['sqlite']['records']} config records)")
        print(f"Redis:  {'✓' if health['redis']['available'] else '✗'} "
              f"({health['redis']['keys']} keys)")
        
        return health['sqlite']['available']
    else:
        return initializer.run_full_initialization()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
