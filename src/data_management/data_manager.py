"""
Data Manager
Main coordinator for all data management operations
"""

import asyncio
import logging
import json
from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
from pathlib import Path

from .cache_manager import CacheManager
from .database_manager import DatabaseManager
from .state_manager import StateManager
from .analytics_engine import AnalyticsEngine
from .models import (
    SensorReading, NavigationData, OperationalState, PerformanceMetric,
    OperationalLog, ConfigurationData, DataType
)


class DataManager:
    """Main data management coordinator providing unified access to all data operations"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.config = config or {}
        redis_config = self.config.get('redis', {})
        db_path = self.config.get('database_path', '/var/lib/lawnberry/data.db')
        
        # Initialize components
        self.cache = CacheManager(redis_config)
        self.database = DatabaseManager(db_path)
        self.state = StateManager(self.cache, self.database)
        self.analytics = AnalyticsEngine(self.cache, self.database)
        
        # MQTT integration for pub/sub bridge
        self._mqtt_client = None
        self._mqtt_subscriptions = {}
        
        # Data export and backup
        self.backup_path = Path(self.config.get('backup_path', '/var/backups/lawnberry'))
        self.backup_path.mkdir(parents=True, exist_ok=True)
        
        # Performance monitoring
        self.performance_stats = {
            'total_operations': 0,
            'cache_operations': 0,
            'database_operations': 0,
            'errors': 0,
            'avg_response_time': 0.0
        }
        
        # Data lifecycle management
        self._cleanup_task: Optional[asyncio.Task] = None
        self._backup_task: Optional[asyncio.Task] = None
        
        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize all data management components"""
        try:
            self.logger.info("Initializing data management system...")
            
            # Initialize components in order
            if not await self.cache.connect():
                self.logger.error("Failed to initialize cache manager")
                return False
            
            if not await self.database.initialize():
                self.logger.error("Failed to initialize database manager")
                return False
            
            if not await self.state.initialize():
                self.logger.error("Failed to initialize state manager")
                return False
            
            if not await self.analytics.initialize():
                self.logger.error("Failed to initialize analytics engine")
                return False
            
            # Start background tasks
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self._backup_task = asyncio.create_task(self._backup_loop())
            
            self._initialized = True
            self.logger.info("Data management system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Data management initialization failed: {e}")
            return False

    # Convenience lifecycle wrappers for services that expect start/stop
    async def start(self) -> bool:
        """Alias for initialize() to satisfy existing service code."""
        return await self.initialize()

    async def stop(self) -> None:
        """Alias for shutdown() to satisfy existing service code."""
        await self.shutdown()
    
    # Sensor Data Operations
    async def store_sensor_reading(self, reading: SensorReading) -> bool:
        """Store sensor reading with caching and analytics integration"""
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Cache for fast access
            cache_key = f"{reading.sensor_id}_{reading.timestamp.isoformat()}"
            await self.cache.set(DataType.SENSOR, cache_key, reading.to_dict())
            
            # Store in database for persistence
            success = await self.database.store_sensor_reading(reading)
            
            # Add to analytics engine
            await self.analytics.add_sensor_data(reading)
            
            # Update performance stats
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            await self._update_performance_stats('store_sensor_reading', response_time, success)
            
            # Trigger events
            await self._trigger_event('sensor_data_stored', {
                'sensor_id': reading.sensor_id,
                'sensor_type': reading.sensor_type,
                'success': success
            })
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error storing sensor reading: {e}")
            self.performance_stats['errors'] += 1
            return False
    
    async def get_sensor_readings(self, sensor_id: str = None, sensor_type: str = None,
                                 start_time: datetime = None, end_time: datetime = None,
                                 limit: int = 1000, use_cache: bool = True) -> List[SensorReading]:
        """Get sensor readings with intelligent caching"""
        try:
            start_op_time = asyncio.get_event_loop().time()
            
            # Try cache first for recent data
            if use_cache and start_time and start_time > datetime.now() - timedelta(hours=1):
                cache_pattern = f"{sensor_id or '*'}_{sensor_type or '*'}"
                cached_data = await self.cache.get_pattern(DataType.SENSOR, cache_pattern)
                
                if cached_data:
                    readings = [SensorReading.from_dict(data) for data in cached_data.values()]
                    # Filter cached results
                    filtered_readings = self._filter_readings(readings, sensor_id, sensor_type, 
                                                            start_time, end_time, limit)
                    
                    if len(filtered_readings) >= min(limit, 100):  # Good cache hit
                        response_time = (asyncio.get_event_loop().time() - start_op_time) * 1000
                        await self._update_performance_stats('get_sensor_readings_cache', response_time, True)
                        return filtered_readings
            
            # Fall back to database
            readings = await self.database.get_sensor_readings(
                sensor_id, sensor_type, start_time, end_time, limit
            )
            
            response_time = (asyncio.get_event_loop().time() - start_op_time) * 1000
            await self._update_performance_stats('get_sensor_readings_db', response_time, True)
            
            return readings
            
        except Exception as e:
            self.logger.error(f"Error getting sensor readings: {e}")
            self.performance_stats['errors'] += 1
            return []
    
    def _filter_readings(self, readings: List[SensorReading], sensor_id: str = None,
                        sensor_type: str = None, start_time: datetime = None,
                        end_time: datetime = None, limit: int = 1000) -> List[SensorReading]:
        """Filter readings based on criteria"""
        filtered = readings
        
        if sensor_id:
            filtered = [r for r in filtered if r.sensor_id == sensor_id]
        
        if sensor_type:
            filtered = [r for r in filtered if r.sensor_type == sensor_type]
        
        if start_time:
            filtered = [r for r in filtered if r.timestamp >= start_time]
        
        if end_time:
            filtered = [r for r in filtered if r.timestamp <= end_time]
        
        # Sort by timestamp descending and limit
        filtered.sort(key=lambda r: r.timestamp, reverse=True)
        return filtered[:limit]
    
    # State Management Operations
    async def get_current_state(self) -> OperationalState:
        """Get current operational state"""
        return await self.state.get_current_state()
    
    async def update_system_state(self, **kwargs) -> bool:
        """Update system operational state"""
        return await self.state.update_state(**kwargs)
    
    async def emergency_stop(self, reason: str = "Emergency stop triggered"):
        """Trigger emergency stop"""
        await self.state.emergency_stop(reason)
        
        # Trigger emergency event
        await self._trigger_event('emergency_stop', {
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
    
    # Configuration Management
    async def get_configuration(self, section: str = None, key: str = None) -> Union[List[ConfigurationData], Any]:
        """Get configuration data with caching"""
        try:
            # Try cache first
            if section and key:
                cache_key = f"{section}_{key}"
                cached_config = await self.cache.get(DataType.CONFIGURATION, cache_key)
                if cached_config:
                    return ConfigurationData.from_dict(cached_config).value
            
            # Get from database
            configs = await self.database.get_configurations(section)
            
            if key:
                matching_configs = [c for c in configs if c.key == key]
                if matching_configs:
                    config = matching_configs[0]
                    # Cache for future access
                    cache_key = f"{section}_{key}"
                    await self.cache.set(DataType.CONFIGURATION, cache_key, config.to_dict())
                    return config.value
                return None
            
            return configs
            
        except Exception as e:
            self.logger.error(f"Error getting configuration: {e}")
            return [] if not key else None
    
    async def set_configuration(self, section: str, key: str, value: Any, 
                               data_type: str = "str", metadata: Dict[str, Any] = None) -> bool:
        """Set configuration data"""
        try:
            config_id = f"{section}_{key}"
            config = ConfigurationData(
                config_id=config_id,
                section=section,
                key=key,
                value=value,
                data_type=data_type,
                metadata=metadata or {}
            )
            
            # Store in database
            success = await self.database.store_configuration(config)
            
            if success:
                # Update cache
                cache_key = f"{section}_{key}"
                await self.cache.set(DataType.CONFIGURATION, cache_key, config.to_dict())
                
                # Trigger configuration change event
                await self._trigger_event('configuration_changed', {
                    'section': section,
                    'key': key,
                    'value': value
                })
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error setting configuration: {e}")
            return False
    
    # Analytics and Reporting
    async def get_performance_report(self, time_window: timedelta = None) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        return await self.analytics.generate_performance_report(time_window)
    
    async def get_maintenance_predictions(self) -> List[Dict[str, Any]]:
        """Get predictive maintenance recommendations"""
        return await self.analytics.predict_maintenance_needs()
    
    async def calculate_coverage_efficiency(self, time_window: timedelta = None) -> float:
        """Calculate mowing coverage efficiency"""
        result = await self.analytics.calculate_coverage_efficiency(time_window)
        return result.value
    
    # Data Export and Backup
    async def export_data(self, data_types: List[str] = None, 
                         start_time: datetime = None, end_time: datetime = None,
                         format: str = "json") -> str:
        """Export data to file"""
        try:
            export_data = {}
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Default to all data types
            if not data_types:
                data_types = ["sensor_readings", "navigation_data", "operational_states", 
                             "configurations", "performance_metrics"]
            
            # Export sensor readings
            if "sensor_readings" in data_types:
                readings = await self.database.get_sensor_readings(
                    start_time=start_time, end_time=end_time, limit=10000
                )
                export_data["sensor_readings"] = [r.to_dict() for r in readings]
            
            # Export configurations
            if "configurations" in data_types:
                configs = await self.database.get_configurations()
                export_data["configurations"] = [c.to_dict() for c in configs]
            
            # Add metadata
            export_data["metadata"] = {
                "export_timestamp": datetime.now().isoformat(),
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "data_types": data_types,
                "format": format
            }
            
            # Save to file
            filename = f"lawnberry_export_{timestamp}.{format}"
            filepath = self.backup_path / filename
            
            if format == "json":
                with open(filepath, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            self.logger.info(f"Data exported to {filepath}")
            return str(filepath)
            
        except Exception as e:
            self.logger.error(f"Data export failed: {e}")
            raise
    
    async def backup_system_data(self) -> str:
        """Create complete system backup"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"lawnberry_backup_{timestamp}.db"
            backup_filepath = self.backup_path / backup_filename
            
            # Backup database
            success = await self.database.backup_database(str(backup_filepath))
            
            if success:
                self.logger.info(f"System backup created: {backup_filepath}")
                return str(backup_filepath)
            else:
                raise Exception("Database backup failed")
                
        except Exception as e:
            self.logger.error(f"System backup failed: {e}")
            raise
    
    # Event System
    def register_event_handler(self, event_type: str, handler: Callable):
        """Register event handler"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def _trigger_event(self, event_type: str, data: Dict[str, Any]):
        """Trigger event handlers"""
        try:
            handlers = self._event_handlers.get(event_type, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event_type, data)
                    else:
                        handler(event_type, data)
                except Exception as e:
                    self.logger.error(f"Event handler error for {event_type}: {e}")
        except Exception as e:
            self.logger.error(f"Event triggering error: {e}")
    
    # Background Tasks
    async def _cleanup_loop(self):
        """Background cleanup task"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Cleanup old data
                cleanup_results = await self.database.cleanup_old_data()
                if cleanup_results:
                    total_cleaned = sum(v for v in cleanup_results.values() if isinstance(v, int))
                    self.logger.info(f"Cleaned up {total_cleaned} old records")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Cleanup loop error: {e}")
    
    async def _backup_loop(self):
        """Background backup task"""
        while True:
            try:
                await asyncio.sleep(86400)  # Run daily
                
                # Create daily backup
                await self.backup_system_data()
                
                # Clean old backups (keep 30 days)
                cutoff_date = datetime.now() - timedelta(days=30)
                for backup_file in self.backup_path.glob("lawnberry_backup_*.db"):
                    if backup_file.stat().st_mtime < cutoff_date.timestamp():
                        backup_file.unlink()
                        self.logger.info(f"Deleted old backup: {backup_file}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Backup loop error: {e}")
    
    async def _update_performance_stats(self, operation: str, response_time: float, success: bool):
        """Update performance statistics"""
        self.performance_stats['total_operations'] += 1
        
        if 'cache' in operation:
            self.performance_stats['cache_operations'] += 1
        elif 'db' in operation:
            self.performance_stats['database_operations'] += 1
        
        if not success:
            self.performance_stats['errors'] += 1
        
        # Update average response time
        current_avg = self.performance_stats['avg_response_time']
        total_ops = self.performance_stats['total_operations']
        self.performance_stats['avg_response_time'] = (
            (current_avg * (total_ops - 1) + response_time) / total_ops
        )
        
        # Log slow operations
        if response_time > 100:  # 100ms threshold
            self.logger.warning(f"Slow operation {operation}: {response_time:.2f}ms")
    
    # System Status and Health
    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        try:
            # Get component health
            cache_stats = await self.cache.get_stats()
            db_stats = await self.database.get_statistics()
            state_info = await self.state.get_session_info()
            
            # Calculate overall health score
            health_score = 100.0
            
            # Cache health
            if not cache_stats['connected']:
                health_score -= 20
            elif cache_stats['hit_rate'] < 50:
                health_score -= 10
            
            # Database health
            if not db_stats:
                health_score -= 30
            
            # Response time health
            if self.performance_stats['avg_response_time'] > 50:  # 50ms threshold
                health_score -= 15
            
            # Error rate health
            if self.performance_stats['total_operations'] > 0:
                error_rate = self.performance_stats['errors'] / self.performance_stats['total_operations']
                if error_rate > 0.05:  # 5% error rate
                    health_score -= 25
            
            return {
                'overall_health_score': max(0, health_score),
                'status': 'healthy' if health_score > 80 else 'degraded' if health_score > 50 else 'critical',
                'components': {
                    'cache': cache_stats,
                    'database': db_stats,
                    'state_manager': state_info,
                    'performance': self.performance_stats
                },
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"System health check failed: {e}")
            return {
                'overall_health_score': 0,
                'status': 'critical',
                'error': str(e),
                'last_updated': datetime.now().isoformat()
            }
    
    async def shutdown(self):
        """Graceful shutdown of data management system"""
        try:
            self.logger.info("Shutting down data management system...")
            
            # Cancel background tasks
            if self._cleanup_task:
                self._cleanup_task.cancel()
            if self._backup_task:
                self._backup_task.cancel()
            
            # Wait for tasks to complete
            tasks = [t for t in [self._cleanup_task, self._backup_task] if t]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            
            # Shutdown components
            await self.analytics.shutdown()
            await self.state.shutdown()
            await self.database.close()
            await self.cache.disconnect()
            
            self.logger.info("Data management system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during data management shutdown: {e}")
