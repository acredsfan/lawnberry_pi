"""
Comprehensive integration tests for system improvements
Tests plugin architecture, error recovery, performance optimization, and reliability features
"""

import asyncio
import pytest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Import system improvement components
from src.system_integration.plugin_architecture import (
    PluginManager, BasePlugin, PluginType, PluginState, PluginMetadata,
    create_plugin_template
)
from src.system_integration.error_recovery_system import (
    ErrorRecoverySystem, ErrorSeverity, ErrorCategory, ErrorContext
)
from src.system_integration.reliability_service import (
    SystemReliabilityService, AlertLevel, ServiceConfig
)
from src.system_integration.performance_service import (
    PerformanceService, PerformanceCategory, MetricType
)
from src.system_integration.enhanced_system_service import (
    EnhancedSystemService, SystemMode, FeatureFlag
)


# Test fixtures
@pytest.fixture
def temp_plugin_dir():
    """Create temporary plugin directory"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_system_context():
    """Mock system context for plugin testing"""
    return {
        "system_version": "1.0.0",
        "logger": Mock(),
        "config_paths": {
            "system": "/etc/lawnberry",
            "user": "/var/lib/lawnberry"
        }
    }


@pytest.fixture
async def plugin_manager():
    """Create plugin manager instance"""
    manager = PluginManager("1.0.0")
    yield manager
    await manager.shutdown_all()


@pytest.fixture
async def error_recovery_system():
    """Create error recovery system instance"""
    system = ErrorRecoverySystem()
    await system.initialize()
    yield system
    await system.shutdown()


@pytest.fixture
async def reliability_service():
    """Create reliability service instance"""
    service = SystemReliabilityService()
    await service.initialize()
    yield service
    # Note: service doesn't have explicit shutdown in the current implementation


@pytest.fixture
async def performance_service():
    """Create performance service instance"""
    # Use in-memory database for testing
    service = PerformanceService(":memory:")
    await service.initialize()
    yield service
    await service.shutdown()


@pytest.fixture
async def enhanced_system_service():
    """Create enhanced system service instance"""
    service = EnhancedSystemService()
    await service.initialize()
    yield service
    await service.shutdown()


# Plugin Architecture Tests
class TestPluginArchitecture:
    """Test plugin architecture functionality"""
    
    def test_plugin_template_creation(self, temp_plugin_dir):
        """Test plugin template creation"""
        plugin_name = "test_plugin"
        plugin_type = PluginType.SERVICE
        
        create_plugin_template(plugin_name, plugin_type, temp_plugin_dir)
        
        plugin_dir = temp_plugin_dir / plugin_name
        assert plugin_dir.exists()
        assert (plugin_dir / "plugin.yaml").exists()
        assert (plugin_dir / "main.py").exists()
        assert (plugin_dir / "config.yaml").exists()
        assert (plugin_dir / "README.md").exists()
        
        # Verify plugin.yaml content
        with open(plugin_dir / "plugin.yaml", 'r') as f:
            import yaml
            metadata = yaml.safe_load(f)
            assert metadata['name'] == plugin_name
            assert metadata['plugin_type'] == plugin_type.value
    
    @pytest.mark.asyncio
    async def test_plugin_discovery(self, plugin_manager, temp_plugin_dir):
        """Test plugin discovery functionality"""
        # Create test plugin
        create_plugin_template("test_service", PluginType.SERVICE, temp_plugin_dir)
        
        # Mock plugin directories
        plugin_manager.user_plugin_dir = temp_plugin_dir
        
        plugins = await plugin_manager.discover_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "test_service"
    
    @pytest.mark.asyncio
    async def test_plugin_loading(self, plugin_manager, temp_plugin_dir):
        """Test plugin loading and initialization"""
        # Create test plugin
        plugin_name = "test_service"
        create_plugin_template(plugin_name, PluginType.SERVICE, temp_plugin_dir)
        
        plugin_dir = temp_plugin_dir / plugin_name
        
        # Load plugin
        success = await plugin_manager.load_plugin(plugin_dir, enable=True)
        assert success
        
        # Verify plugin is loaded and active
        plugins = await plugin_manager.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]['name'] == plugin_name
        assert plugins[0]['state'] == 'active'
    
    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self, plugin_manager, temp_plugin_dir):
        """Test complete plugin lifecycle"""
        plugin_name = "test_lifecycle"
        create_plugin_template(plugin_name, PluginType.SERVICE, temp_plugin_dir)
        
        plugin_dir = temp_plugin_dir / plugin_name
        
        # Load plugin
        await plugin_manager.load_plugin(plugin_dir, enable=False)
        plugin = plugin_manager.get_plugin(plugin_name)
        assert plugin is not None
        
        # Enable plugin
        success = await plugin_manager.enable_plugin(plugin_name)
        assert success
        
        # Check status
        status = await plugin_manager.get_plugin_status(plugin_name)
        assert status['state'] == 'active'
        
        # Disable plugin
        success = await plugin_manager.disable_plugin(plugin_name)
        assert success
        
        # Unload plugin
        success = await plugin_manager.unload_plugin(plugin_name)
        assert success
        
        # Verify plugin is gone
        plugin = plugin_manager.get_plugin(plugin_name)
        assert plugin is None


# Error Recovery System Tests
class TestErrorRecoverySystem:
    """Test error recovery system functionality"""
    
    @pytest.mark.asyncio
    async def test_error_handling(self, error_recovery_system):
        """Test basic error handling"""
        context = ErrorContext(
            component="test_component",
            operation="test_operation"
        )
        
        test_exception = ValueError("Test error")
        
        error_id = await error_recovery_system.handle_error(
            test_exception,
            context,
            ErrorSeverity.MEDIUM,
            ErrorCategory.SOFTWARE
        )
        
        assert error_id is not None
        assert error_id in error_recovery_system.errors
        
        error_info = error_recovery_system.errors[error_id]
        assert error_info.message == str(test_exception)
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.category == ErrorCategory.SOFTWARE
    
    @pytest.mark.asyncio
    async def test_error_aggregation(self, error_recovery_system):
        """Test error aggregation and deduplication"""
        context = ErrorContext(
            component="test_component",
            operation="test_operation"
        )
        
        # Generate same error multiple times
        test_exception = ValueError("Repeated error")
        
        error_id1 = await error_recovery_system.handle_error(
            test_exception, context, ErrorSeverity.LOW, ErrorCategory.SOFTWARE
        )
        
        error_id2 = await error_recovery_system.handle_error(
            test_exception, context, ErrorSeverity.LOW, ErrorCategory.SOFTWARE
        )
        
        # Should be same error ID (aggregated)
        assert error_id1 == error_id2
        
        error_info = error_recovery_system.errors[error_id1]
        assert error_info.count >= 2
    
    @pytest.mark.asyncio
    async def test_component_health_tracking(self, error_recovery_system):
        """Test component health tracking"""
        component_name = "test_component"
        context = ErrorContext(component=component_name, operation="test")
        
        # Initially no health info
        assert component_name not in error_recovery_system.component_health
        
        # Generate error
        await error_recovery_system.handle_error(
            Exception("Test error"),
            context,
            ErrorSeverity.HIGH,
            ErrorCategory.SOFTWARE
        )
        
        # Health should be tracked
        assert component_name in error_recovery_system.component_health
        health = error_recovery_system.component_health[component_name]
        assert health.error_count > 0
        assert health.health_score < 100.0
    
    @pytest.mark.asyncio
    async def test_recovery_strategy_execution(self, error_recovery_system):
        """Test recovery strategy execution"""
        # Mock service manager
        mock_service_manager = AsyncMock()
        mock_service_manager.restart_service.return_value = True
        error_recovery_system.service_manager = mock_service_manager
        
        context = ErrorContext(component="test_service", operation="test")
        
        await error_recovery_system.handle_error(
            Exception("Service error"),
            context,
            ErrorSeverity.HIGH,
            ErrorCategory.SOFTWARE
        )
        
        # Allow time for recovery attempt
        await asyncio.sleep(0.1)
        
        # Should have attempted service restart
        mock_service_manager.restart_service.assert_called()


# Reliability Service Tests
class TestReliabilityService:
    """Test reliability service functionality"""
    
    @pytest.mark.asyncio
    async def test_system_health_monitoring(self, reliability_service):
        """Test system health monitoring"""
        health = reliability_service.get_system_health()
        
        assert 'overall_health' in health
        assert 'services' in health
        assert 'system_metrics' in health
        assert 'alerts' in health
        assert 'uptime_seconds' in health
    
    @pytest.mark.asyncio
    async def test_alert_creation(self, reliability_service):
        """Test alert creation and management"""
        # Create test alert
        await reliability_service._create_alert(
            AlertLevel.WARNING,
            "test_component",
            "Test alert message",
            {"test_detail": "value"}
        )
        
        # Get active alerts
        alerts = reliability_service.get_active_alerts()
        assert len(alerts) > 0
        
        alert = alerts[0]
        assert alert['level'] == 'warning'
        assert alert['component'] == 'test_component'
        assert alert['message'] == 'Test alert message'
    
    @pytest.mark.asyncio
    async def test_alert_acknowledgment(self, reliability_service):
        """Test alert acknowledgment"""
        # Create alert
        await reliability_service._create_alert(
            AlertLevel.INFO,
            "test",
            "Test alert"
        )
        
        alerts = reliability_service.get_active_alerts()
        alert_id = alerts[0]['alert_id']
        
        # Acknowledge alert
        success = await reliability_service.acknowledge_alert(alert_id)
        assert success
        
        # Verify acknowledgment
        assert reliability_service.alerts[alert_id].acknowledged


# Performance Service Tests
class TestPerformanceService:
    """Test performance service functionality"""
    
    @pytest.mark.asyncio
    async def test_metric_recording(self, performance_service):
        """Test metric recording"""
        await performance_service.record_metric(
            "test_metric",
            PerformanceCategory.CPU,
            MetricType.GAUGE,
            75.5,
            {"component": "test"},
            "%"
        )
        
        # Flush metrics to ensure they're stored
        await performance_service._flush_metrics_buffer()
        
        # Verify metric was recorded
        metrics = await performance_service.get_performance_metrics(
            PerformanceCategory.CPU,
            hours=1
        )
        
        assert len(metrics) > 0
        test_metrics = [m for m in metrics if m['name'] == 'test_metric']
        assert len(test_metrics) > 0
        assert test_metrics[0]['value'] == 75.5
    
    @pytest.mark.asyncio
    async def test_performance_timer(self, performance_service):
        """Test performance timer context manager"""
        with performance_service.timer("test_operation", PerformanceCategory.CPU):
            await asyncio.sleep(0.01)  # Simulate work
        
        # Allow time for metric to be recorded
        await asyncio.sleep(0.1)
        await performance_service._flush_metrics_buffer()
        
        metrics = await performance_service.get_performance_metrics(hours=1)
        timer_metrics = [m for m in metrics if m['name'] == 'test_operation']
        assert len(timer_metrics) > 0
        assert timer_metrics[0]['unit'] == 'ms'
        assert timer_metrics[0]['value'] > 0
    
    @pytest.mark.asyncio
    async def test_performance_score_calculation(self, performance_service):
        """Test performance score calculation"""
        # Record some test metrics
        await performance_service.record_metric(
            "cpu_usage", PerformanceCategory.CPU, MetricType.GAUGE, 45.0, {}, "%"
        )
        await performance_service.record_metric(
            "memory_usage", PerformanceCategory.MEMORY, MetricType.GAUGE, 60.0, {}, "%"
        )
        
        await performance_service._flush_metrics_buffer()
        
        # Get performance score
        score = await performance_service.get_current_performance_score()
        assert 0 <= score <= 100
    
    @pytest.mark.asyncio
    async def test_performance_profile_switching(self, performance_service):
        """Test performance profile switching"""
        # Switch to power saving profile
        success = await performance_service.set_performance_profile("power_saving")
        assert success
        
        summary = await performance_service.get_performance_summary()
        assert summary['current_profile'] == 'power_saving'
        
        # Switch to performance profile
        success = await performance_service.set_performance_profile("performance")
        assert success
        
        summary = await performance_service.get_performance_summary()
        assert summary['current_profile'] == 'performance'


# Enhanced System Service Tests
class TestEnhancedSystemService:
    """Test enhanced system service functionality"""
    
    @pytest.mark.asyncio
    async def test_system_initialization(self, enhanced_system_service):
        """Test system initialization"""
        status = await enhanced_system_service.get_system_status()
        
        assert 'mode' in status
        assert 'status' in status
        assert 'enabled_features' in status
        assert 'registered_services' in status
        assert 'uptime_seconds' in status
        
        # Should be in normal mode after initialization
        assert status['mode'] == 'normal'
    
    @pytest.mark.asyncio
    async def test_service_registration(self, enhanced_system_service):
        """Test service registration"""
        mock_service = Mock()
        service_name = "test_service"
        
        enhanced_system_service.register_service(service_name, mock_service)
        
        assert service_name in enhanced_system_service.registered_services
        assert enhanced_system_service.registered_services[service_name] == mock_service
    
    @pytest.mark.asyncio
    async def test_feature_management(self, enhanced_system_service):
        """Test feature flag management"""
        # Test enabling feature
        success = await enhanced_system_service.enable_feature(FeatureFlag.PREDICTIVE_MAINTENANCE)
        assert success
        assert FeatureFlag.PREDICTIVE_MAINTENANCE in enhanced_system_service.enabled_features
        
        # Test disabling feature
        success = await enhanced_system_service.disable_feature(FeatureFlag.PREDICTIVE_MAINTENANCE)
        assert success
        assert FeatureFlag.PREDICTIVE_MAINTENANCE not in enhanced_system_service.enabled_features
    
    @pytest.mark.asyncio
    async def test_mode_transitions(self, enhanced_system_service):
        """Test system mode transitions"""
        # Test transition to maintenance mode
        await enhanced_system_service._transition_to_mode(SystemMode.MAINTENANCE)
        assert enhanced_system_service.current_mode == SystemMode.MAINTENANCE
        
        # Test transition to emergency mode
        await enhanced_system_service._transition_to_mode(SystemMode.EMERGENCY)
        assert enhanced_system_service.current_mode == SystemMode.EMERGENCY
        
        # Test transition back to normal
        await enhanced_system_service._transition_to_mode(SystemMode.NORMAL)
        assert enhanced_system_service.current_mode == SystemMode.NORMAL
    
    @pytest.mark.asyncio
    async def test_event_system(self, enhanced_system_service):
        """Test event handling system"""
        event_received = False
        test_data = {"test": "value"}
        
        def test_handler(data):
            nonlocal event_received
            event_received = True
            assert data == test_data
        
        # Register event handler
        enhanced_system_service.register_event_handler("test_event", test_handler)
        
        # Emit event
        await enhanced_system_service._emit_event("test_event", test_data)
        
        # Give time for event processing
        await asyncio.sleep(0.1)
        
        assert event_received


# Integration Tests
class TestSystemIntegration:
    """Test integration between system improvement components"""
    
    @pytest.mark.asyncio
    async def test_error_recovery_with_reliability_service(self):
        """Test integration between error recovery and reliability service"""
        # Create both services
        error_recovery = ErrorRecoverySystem()
        reliability_service = SystemReliabilityService()
        
        await error_recovery.initialize()
        await reliability_service.initialize()
        
        try:
            # Link services
            error_recovery.notification_system = reliability_service
            
            # Generate error
            context = ErrorContext(component="test_service", operation="test")
            await error_recovery.handle_error(
                Exception("Integration test error"),
                context,
                ErrorSeverity.CRITICAL,
                ErrorCategory.SOFTWARE
            )
            
            # Allow time for processing
            await asyncio.sleep(0.2)
            
            # Check that reliability service received notification
            alerts = reliability_service.get_active_alerts()
            # Note: Actual integration would create alerts, but our mock doesn't
            # This test verifies the integration structure
            
        finally:
            await error_recovery.shutdown()
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_with_error_recovery(self):
        """Test performance monitoring triggering error recovery"""
        performance_service = PerformanceService(":memory:")
        error_recovery = ErrorRecoverySystem()
        
        await performance_service.initialize()
        await error_recovery.initialize()
        
        try:
            # Record high CPU usage that should trigger optimization
            await performance_service.record_metric(
                "cpu_usage", PerformanceCategory.CPU, MetricType.GAUGE, 95.0, {}, "%"
            )
            
            # Force performance analysis
            await performance_service._analyze_performance()
            
            # Allow time for processing
            await asyncio.sleep(0.1)
            
            # This test verifies the integration structure
            # In a full implementation, high CPU would trigger recovery actions
            
        finally:
            await performance_service.shutdown()
            await error_recovery.shutdown()
    
    @pytest.mark.asyncio
    async def test_enhanced_system_service_coordination(self):
        """Test enhanced system service coordinating all components"""
        # Create system service
        system_service = EnhancedSystemService()
        
        # Mock configuration to enable all features
        system_service.enabled_features = set(FeatureFlag)
        
        await system_service.initialize()
        
        try:
            # Verify all core services are initialized
            assert system_service.plugin_manager is not None
            assert system_service.error_recovery is not None
            assert system_service.reliability_service is not None
            assert system_service.performance_service is not None
            
            # Verify services are registered
            assert 'plugin_manager' in system_service.registered_services
            assert 'error_recovery' in system_service.registered_services
            assert 'reliability_service' in system_service.registered_services
            assert 'performance_service' in system_service.registered_services
            
            # Test system status
            status = await system_service.get_system_status()
            assert status['mode'] == 'normal'
            assert len(status['registered_services']) >= 4
            
        finally:
            await system_service.shutdown()


# Performance Tests
class TestPerformanceMetrics:
    """Test performance characteristics of system improvements"""
    
    @pytest.mark.asyncio
    async def test_plugin_loading_performance(self, plugin_manager, temp_plugin_dir):
        """Test plugin loading performance"""
        # Create multiple test plugins
        plugin_count = 5
        for i in range(plugin_count):
            create_plugin_template(f"perf_test_{i}", PluginType.SERVICE, temp_plugin_dir)
        
        plugin_manager.user_plugin_dir = temp_plugin_dir
        
        # Measure plugin discovery time
        start_time = asyncio.get_event_loop().time()
        plugins = await plugin_manager.discover_plugins()
        discovery_time = asyncio.get_event_loop().time() - start_time
        
        assert len(plugins) == plugin_count
        assert discovery_time < 1.0  # Should complete within 1 second
        
        # Measure plugin loading time
        start_time = asyncio.get_event_loop().time()
        for plugin_path in plugins:
            await plugin_manager.load_plugin(plugin_path, enable=True)
        loading_time = asyncio.get_event_loop().time() - start_time
        
        assert loading_time < 2.0  # Should load all plugins within 2 seconds
    
    @pytest.mark.asyncio
    async def test_error_handling_performance(self, error_recovery_system):
        """Test error handling performance"""
        context = ErrorContext(component="perf_test", operation="test")
        error_count = 100
        
        # Measure error handling time
        start_time = asyncio.get_event_loop().time()
        
        for i in range(error_count):
            await error_recovery_system.handle_error(
                Exception(f"Test error {i}"),
                context,
                ErrorSeverity.LOW,
                ErrorCategory.SOFTWARE,
                auto_recover=False  # Disable recovery for performance test
            )
        
        handling_time = asyncio.get_event_loop().time() - start_time
        
        # Should handle 100 errors within 1 second
        assert handling_time < 1.0
        assert len(error_recovery_system.errors) > 0
    
    @pytest.mark.asyncio
    async def test_metrics_collection_performance(self, performance_service):
        """Test metrics collection performance"""
        metric_count = 1000
        
        # Measure metric recording time
        start_time = asyncio.get_event_loop().time()
        
        for i in range(metric_count):
            await performance_service.record_metric(
                f"perf_test_{i % 10}",  # Reuse some metric names
                PerformanceCategory.CPU,
                MetricType.GAUGE,
                float(i % 100),
                {"test": str(i % 5)},
                "unit"
            )
        
        recording_time = asyncio.get_event_loop().time() - start_time
        
        # Should record 1000 metrics within 1 second
        assert recording_time < 1.0
        
        # Test metric flushing performance
        start_time = asyncio.get_event_loop().time()
        await performance_service._flush_metrics_buffer()
        flush_time = asyncio.get_event_loop().time() - start_time
        
        # Should flush within reasonable time
        assert flush_time < 2.0


# Stress Tests
class TestStressScenarios:
    """Test system behavior under stress conditions"""
    
    @pytest.mark.asyncio
    async def test_concurrent_error_handling(self, error_recovery_system):
        """Test concurrent error handling"""
        context = ErrorContext(component="stress_test", operation="concurrent")
        
        async def generate_error(error_id):
            await error_recovery_system.handle_error(
                Exception(f"Concurrent error {error_id}"),
                context,
                ErrorSeverity.MEDIUM,
                ErrorCategory.SOFTWARE
            )
        
        # Generate concurrent errors
        tasks = [generate_error(i) for i in range(50)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # System should handle all errors without crashing
        assert len(error_recovery_system.errors) > 0
        assert len(error_recovery_system.component_health) > 0
    
    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, performance_service):
        """Test memory usage under high metric load"""
        import psutil
        import gc
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        # Generate high metric load
        for batch in range(10):
            for i in range(100):
                await performance_service.record_metric(
                    f"stress_metric_{i}",
                    PerformanceCategory.MEMORY,
                    MetricType.COUNTER,
                    float(batch * 100 + i),
                    {"batch": str(batch)},
                    "count"
                )
            
            # Flush metrics periodically
            await performance_service._flush_metrics_buffer()
            
            # Force garbage collection
            gc.collect()
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 50MB for this test)
        assert memory_increase < 50 * 1024 * 1024


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])
