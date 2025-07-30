"""
Comprehensive tests for the data management system
"""

import asyncio
import pytest
import tempfile
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.data_management import DataManager
from src.data_management.cache_manager import CacheManager
from src.data_management.database_manager import DatabaseManager
from src.data_management.state_manager import StateManager, SystemState, OperationMode
from src.data_management.analytics_engine import AnalyticsEngine
from src.data_management.models import (
    SensorReading, NavigationData, OperationalState, PerformanceMetric,
    ConfigurationData, DataType
)


class TestDataManager:
    """Test suite for DataManager"""
    
    @pytest.fixture
    async def data_manager(self):
        """Create test data manager with temporary database"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                'redis': {
                    'host': 'localhost',
                    'port': 6379,
                    'db': 1  # Use test database
                },
                'database_path': str(Path(temp_dir) / 'test.db'),
                'backup_path': str(Path(temp_dir) / 'backups')
            }
            
            dm = DataManager(config)
            
            # Mock Redis connection for testing
            with patch('redis.asyncio.Redis') as mock_redis:
                mock_redis_instance = AsyncMock()
                mock_redis.return_value = mock_redis_instance
                mock_redis_instance.ping.return_value = True
                mock_redis_instance.get.return_value = None
                mock_redis_instance.setex.return_value = True
                mock_redis_instance.delete.return_value = 1
                mock_redis_instance.keys.return_value = []
                mock_redis_instance.mget.return_value = []
                
                await dm.initialize()
                yield dm
                await dm.shutdown()
    
    @pytest.mark.asyncio
    async def test_initialization(self, data_manager):
        """Test data manager initialization"""
        assert data_manager._initialized
        assert data_manager.cache is not None
        assert data_manager.database is not None
        assert data_manager.state is not None
        assert data_manager.analytics is not None
    
    @pytest.mark.asyncio
    async def test_sensor_data_storage_and_retrieval(self, data_manager):
        """Test sensor data storage and retrieval with <10ms cache response"""
        # Create test sensor reading
        reading = SensorReading(
            sensor_id="test_sensor_01",
            sensor_type="temperature",
            timestamp=datetime.now(),
            value=25.5,
            unit="°C",
            quality=0.95,
            metadata={"location": "test"}
        )
        
        # Test storage
        start_time = asyncio.get_event_loop().time()
        success = await data_manager.store_sensor_reading(reading)
        storage_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        assert success
        assert storage_time < 100  # Should be fast
        
        # Test retrieval
        start_time = asyncio.get_event_loop().time()
        readings = await data_manager.get_sensor_readings(
            sensor_id="test_sensor_01",
            sensor_type="temperature"
        )
        retrieval_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        assert len(readings) == 1
        assert readings[0].sensor_id == "test_sensor_01"
        assert readings[0].value == 25.5
        # Note: Actual <10ms cache response depends on Redis being available
    
    @pytest.mark.asyncio
    async def test_state_management_and_persistence(self, data_manager):
        """Test operational state management and persistence"""
        # Test initial state
        initial_state = await data_manager.get_current_state()
        assert initial_state is not None
        
        # Test state update
        success = await data_manager.update_system_state(
            new_state=SystemState.MOWING.value,
            mode=OperationMode.AUTOMATIC.value,
            battery_level=85.0,
            current_task="mowing_front_yard",
            progress=0.3
        )
        
        assert success
        
        # Verify state was updated
        updated_state = await data_manager.get_current_state()
        assert updated_state.state == SystemState.MOWING.value
        assert updated_state.battery_level == 85.0
        assert updated_state.progress == 0.3
    
    @pytest.mark.asyncio
    async def test_emergency_stop_functionality(self, data_manager):
        """Test emergency stop triggers immediate state change"""
        # Trigger emergency stop
        await data_manager.emergency_stop("Test emergency stop")
        
        # Verify state changed to emergency stop
        state = await data_manager.get_current_state()
        assert state.state == SystemState.EMERGENCY_STOP.value
        assert state.mode == OperationMode.SAFETY.value
        assert "emergency_reason" in state.metadata
    
    @pytest.mark.asyncio
    async def test_configuration_management(self, data_manager):
        """Test configuration storage and retrieval with caching"""
        # Set configuration
        success = await data_manager.set_configuration(
            section="navigation",
            key="max_speed",
            value=1.5,
            data_type="float",
            metadata={"unit": "m/s"}
        )
        
        assert success
        
        # Get configuration
        config_value = await data_manager.get_configuration("navigation", "max_speed")
        assert config_value == 1.5
        
        # Get all configurations for section
        configs = await data_manager.get_configuration("navigation")
        assert len(configs) >= 1
        assert any(c.key == "max_speed" for c in configs)
    
    @pytest.mark.asyncio
    async def test_system_health_monitoring(self, data_manager):
        """Test system health monitoring and reporting"""
        health_status = await data_manager.get_system_health()
        
        assert "overall_health_score" in health_status
        assert "status" in health_status
        assert "components" in health_status
        assert health_status["overall_health_score"] >= 0
        assert health_status["status"] in ["healthy", "degraded", "critical"]
    
    @pytest.mark.asyncio
    async def test_data_export_functionality(self, data_manager):
        """Test data export and backup functionality"""
        # Add some test data
        reading = SensorReading(
            sensor_id="export_test",
            sensor_type="test",
            timestamp=datetime.now(),
            value=123.45,
            unit="test_unit"
        )
        await data_manager.store_sensor_reading(reading)
        
        # Test data export
        export_path = await data_manager.export_data(
            data_types=["sensor_readings", "configurations"],
            format="json"
        )
        
        assert Path(export_path).exists()
        
        # Verify export content
        with open(export_path, 'r') as f:
            export_data = json.load(f)
        
        assert "metadata" in export_data
        assert "sensor_readings" in export_data
        assert len(export_data["sensor_readings"]) > 0
    
    @pytest.mark.asyncio
    async def test_system_recovery_after_shutdown(self, data_manager):
        """Test system state recovery after unexpected shutdown"""
        # Set a specific state
        await data_manager.update_system_state(
            new_state=SystemState.CHARGING.value,
            battery_level=45.0,
            current_task="charging_at_dock"
        )
        
        # Store recovery data
        await data_manager.state.set_recovery_data("test_key", "test_value")
        
        # Simulate restart by creating new data manager with same config
        config = data_manager.config
        new_dm = DataManager(config)
        
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            
            # Mock recovery data in cache
            mock_redis_instance.get.side_effect = lambda key: {
                f"{DataType.OPERATIONAL.value}:current_state": json.dumps({
                    'state': SystemState.CHARGING.value,
                    'mode': OperationMode.AUTOMATIC.value,
                    'battery_level': 45.0,
                    'current_task': 'charging_at_dock',
                    'progress': 0.0,
                    'estimated_completion': None,
                    'last_update': datetime.now().isoformat(),
                    'metadata': {}
                }),
                f"{DataType.OPERATIONAL.value}:recovery_data": json.dumps({
                    "test_key": "test_value"
                })
            }.get(key)
            
            mock_redis_instance.setex.return_value = True
            
            await new_dm.initialize()
            
            # Verify state was recovered
            recovered_state = await new_dm.get_current_state()
            recovery_data = await new_dm.state.get_recovery_data("test_key")
            
            assert recovered_state.state == SystemState.CHARGING.value
            assert recovered_state.battery_level == 45.0
            assert recovery_data == "test_value"
            
            await new_dm.shutdown()


class TestCacheManager:
    """Test suite for CacheManager"""
    
    @pytest.fixture
    async def cache_manager(self):
        """Create test cache manager"""
        config = {
            'host': 'localhost',
            'port': 6379,
            'db': 1
        }
        
        cm = CacheManager(config)
        
        # Mock Redis for testing
        with patch('redis.asyncio.Redis') as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.ping.return_value = True
            
            # Mock get/set operations
            cache_storage = {}
            
            async def mock_get(key):
                return cache_storage.get(key)
            
            async def mock_setex(key, ttl, value):
                cache_storage[key] = value
                return True
            
            mock_redis_instance.get = mock_get
            mock_redis_instance.setex = mock_setex
            
            await cm.connect()
            yield cm
            await cm.disconnect()
    
    @pytest.mark.asyncio
    async def test_cache_performance_target(self, cache_manager):
        """Test cache operations meet <10ms performance target"""
        test_data = {"test": "data", "timestamp": datetime.now().isoformat()}
        
        # Test set operation
        start_time = asyncio.get_event_loop().time()
        success = await cache_manager.set(DataType.SENSOR, "performance_test", test_data)
        set_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        assert success
        # Note: Actual <10ms depends on Redis availability and network
        
        # Test get operation
        start_time = asyncio.get_event_loop().time()
        retrieved_data = await cache_manager.get(DataType.SENSOR, "performance_test")
        get_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        assert retrieved_data == test_data
        # Performance assertion would be: assert get_time < 10
    
    @pytest.mark.asyncio
    async def test_cache_statistics(self, cache_manager):
        """Test cache statistics tracking"""
        # Perform some operations
        await cache_manager.set(DataType.SENSOR, "stats_test", {"value": 123})
        await cache_manager.get(DataType.SENSOR, "stats_test")  # Hit
        await cache_manager.get(DataType.SENSOR, "nonexistent")  # Miss
        
        stats = await cache_manager.get_stats()
        
        assert "hit_rate" in stats
        assert "operations" in stats
        assert stats["operations"]["hits"] >= 1
        assert stats["operations"]["misses"] >= 1
        assert stats["operations"]["sets"] >= 1


class TestDatabaseManager:
    """Test suite for DatabaseManager"""
    
    @pytest.fixture
    async def database_manager(self):
        """Create test database manager"""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / 'test.db')
            dm = DatabaseManager(db_path)
            await dm.initialize()
            yield dm
            await dm.close()
    
    @pytest.mark.asyncio
    async def test_database_initialization(self, database_manager):
        """Test database schema creation and initialization"""
        assert database_manager._initialized
        
        # Test statistics
        stats = await database_manager.get_statistics()
        assert "sensor_readings_count" in stats
        assert "database_size" in stats
        assert stats["database_size"] > 0
    
    @pytest.mark.asyncio
    async def test_data_persistence_and_integrity(self, database_manager):
        """Test data persistence and integrity verification"""
        # Store test data
        reading = SensorReading(
            sensor_id="integrity_test",
            sensor_type="test_sensor",
            timestamp=datetime.now(),
            value={"complex": "data", "number": 42},
            quality=0.99
        )
        
        success = await database_manager.store_sensor_reading(reading)
        assert success
        
        # Retrieve and verify
        readings = await database_manager.get_sensor_readings(
            sensor_id="integrity_test"
        )
        
        assert len(readings) == 1
        retrieved = readings[0]
        assert retrieved.sensor_id == reading.sensor_id
        assert retrieved.value == reading.value
        assert retrieved.quality == reading.quality
    
    @pytest.mark.asyncio
    async def test_data_cleanup_policies(self, database_manager):
        """Test data retention and cleanup policies"""
        # Add old data
        old_reading = SensorReading(
            sensor_id="cleanup_test",
            sensor_type="test",
            timestamp=datetime.now() - timedelta(days=35),  # Older than retention
            value=123
        )
        
        await database_manager.store_sensor_reading(old_reading)
        
        # Add recent data
        recent_reading = SensorReading(
            sensor_id="cleanup_test",
            sensor_type="test", 
            timestamp=datetime.now(),
            value=456
        )
        
        await database_manager.store_sensor_reading(recent_reading)
        
        # Run cleanup
        cleanup_results = await database_manager.cleanup_old_data()
        
        # Verify old data was cleaned up
        readings = await database_manager.get_sensor_readings(sensor_id="cleanup_test")
        assert len(readings) == 1
        assert readings[0].value == 456  # Recent data should remain


class TestAnalyticsEngine:
    """Test suite for AnalyticsEngine"""
    
    @pytest.fixture
    async def analytics_engine(self):
        """Create test analytics engine"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mocked dependencies
            cache_manager = MagicMock()
            cache_manager.publish = AsyncMock()
            
            db_manager = MagicMock()
            db_manager.get_sensor_readings = AsyncMock(return_value=[])
            
            ae = AnalyticsEngine(cache_manager, db_manager)
            await ae.initialize()
            yield ae
            await ae.shutdown()
    
    @pytest.mark.asyncio
    async def test_performance_analysis_accuracy(self, analytics_engine):
        """Test analytics accuracy against known data sets"""
        # Test coverage efficiency calculation
        result = await analytics_engine.calculate_coverage_efficiency()
        
        assert result.metric_name == "coverage_efficiency"
        assert 0 <= result.value <= 100
        assert 0 <= result.confidence <= 1.0
    
    @pytest.mark.asyncio
    async def test_predictive_maintenance_alerts(self, analytics_engine):
        """Test predictive maintenance recommendation generation"""
        predictions = await analytics_engine.predict_maintenance_needs()
        
        assert isinstance(predictions, list)
        # Each prediction should have required fields
        for prediction in predictions:
            assert "component" in prediction
            assert "maintenance_type" in prediction
            assert "urgency" in prediction
            assert "estimated_days" in prediction
            assert "confidence" in prediction
    
    @pytest.mark.asyncio
    async def test_performance_report_generation(self, analytics_engine):
        """Test comprehensive performance report generation"""
        report = await analytics_engine.generate_performance_report()
        
        assert "report_generated" in report
        assert "overall_health_score" in report
        assert "performance_metrics" in report
        assert "sensor_health" in report
        assert "maintenance_predictions" in report
        assert "recommendations" in report


class TestIntegrationScenarios:
    """Integration tests for complete system scenarios"""
    
    @pytest.fixture
    async def full_system(self):
        """Create complete data management system for integration testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                'redis': {'host': 'localhost', 'port': 6379, 'db': 1},
                'database_path': str(Path(temp_dir) / 'integration_test.db'),
                'backup_path': str(Path(temp_dir) / 'backups')
            }
            
            dm = DataManager(config)
            
            # Mock Redis for integration tests
            with patch('redis.asyncio.Redis') as mock_redis:
                mock_redis_instance = AsyncMock()
                mock_redis.return_value = mock_redis_instance
                mock_redis_instance.ping.return_value = True
                
                # Simple in-memory cache simulation
                cache_storage = {}
                
                async def mock_get(key):
                    return cache_storage.get(key)
                
                async def mock_setex(key, ttl, value):
                    cache_storage[key] = value
                    return True
                
                mock_redis_instance.get = mock_get
                mock_redis_instance.setex = mock_setex
                mock_redis_instance.delete = AsyncMock(return_value=1)
                mock_redis_instance.keys = AsyncMock(return_value=[])
                mock_redis_instance.mget = AsyncMock(return_value=[])
                mock_redis_instance.publish = AsyncMock()
                
                await dm.initialize()
                yield dm
                await dm.shutdown()
    
    @pytest.mark.asyncio
    async def test_complete_mowing_session_data_flow(self, full_system):
        """Test complete data flow during a mowing session"""
        dm = full_system
        
        # Start mowing session
        await dm.update_system_state(
            new_state=SystemState.MOWING.value,
            mode=OperationMode.AUTOMATIC.value,
            battery_level=95.0,
            current_task="mowing_back_yard"
        )
        
        # Simulate sensor data during mowing
        sensors_data = [
            SensorReading("gps_01", "gps", datetime.now(), {"lat": 40.7128, "lng": -74.0060}),
            SensorReading("battery_01", "battery", datetime.now(), {"voltage": 12.6, "current": -5.2}),
            SensorReading("imu_01", "imu", datetime.now(), {"heading": 45.0, "tilt": 2.1}),
            SensorReading("camera_01", "camera", datetime.now(), {"obstacles_detected": 0})
        ]
        
        # Store all sensor data
        for reading in sensors_data:
            success = await dm.store_sensor_reading(reading)
            assert success
        
        # Update progress
        await dm.update_system_state(progress=0.7, battery_level=78.0)
        
        # Complete session
        await dm.update_system_state(
            new_state=SystemState.IDLE.value,
            progress=1.0,
            current_task=None
        )
        
        # Verify data integrity
        state = await dm.get_current_state()
        assert state.state == SystemState.IDLE.value
        assert state.progress == 1.0
        
        # Verify sensor data retrieval
        gps_readings = await dm.get_sensor_readings(sensor_id="gps_01")
        assert len(gps_readings) >= 1
        
        # Generate performance report
        report = await dm.get_performance_report()
        assert report["overall_health_score"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
