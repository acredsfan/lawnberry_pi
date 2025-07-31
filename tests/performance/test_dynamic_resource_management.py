"""
Dynamic Resource Management Performance Tests
Comprehensive benchmarking and validation of dynamic resource allocation
"""

import pytest
import asyncio
import time
import psutil
import numpy as np
from typing import Dict, List, Any
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from dataclasses import asdict

# Import the dynamic resource management components
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.system_integration.dynamic_resource_manager import (
    DynamicResourceManager, OperationMode, ResourceMetrics, AllocationDecision
)
from src.system_integration.performance_dashboard import PerformanceDashboard
from src.system_integration.enhanced_system_monitor import EnhancedSystemMonitor


@pytest.fixture
async def resource_manager():
    """Create a dynamic resource manager for testing"""
    manager = DynamicResourceManager()
    await manager.initialize()
    yield manager
    await manager.shutdown()


@pytest.fixture
async def performance_dashboard(resource_manager):
    """Create a performance dashboard for testing"""
    dashboard = PerformanceDashboard(resource_manager)
    await dashboard.initialize()
    yield dashboard
    await dashboard.shutdown()


@pytest.fixture
async def enhanced_monitor():
    """Create an enhanced system monitor for testing"""
    monitor = EnhancedSystemMonitor()
    await monitor.initialize()
    yield monitor
    await monitor.shutdown()


class MockMetrics:
    """Mock system metrics for testing"""
    
    @staticmethod
    def create_high_cpu_metrics():
        return ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=90.0,
            memory_percent=60.0,
            memory_mb=9830.4,
            io_read_mb_s=10.5,
            io_write_mb_s=8.2,
            network_bytes_s=1024000,
            load_average=[3.5, 3.2, 2.8],
            temperature=75.0
        )
    
    @staticmethod
    def create_high_memory_metrics():
        return ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=45.0,
            memory_percent=85.0,
            memory_mb=13926.4,
            io_read_mb_s=15.2,
            io_write_mb_s=12.1,
            network_bytes_s=2048000,
            load_average=[1.8, 2.1, 2.0],
            temperature=68.0
        )
    
    @staticmethod
    def create_low_usage_metrics():
        return ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=25.0,
            memory_percent=40.0,
            memory_mb=6553.6,
            io_read_mb_s=2.1,
            io_write_mb_s=1.8,
            network_bytes_s=512000,
            load_average=[0.8, 0.9, 1.0],
            temperature=55.0
        )


@pytest.mark.asyncio
class TestDynamicResourceManager:
    """Test dynamic resource manager functionality"""
    
    async def test_initialization(self, resource_manager):
        """Test resource manager initialization"""
        # Verify initialization
        assert resource_manager.monitoring_active
        assert len(resource_manager.service_profiles) > 0
        assert len(resource_manager.current_allocations) > 0
        
        # Verify critical services are configured
        assert 'safety' in resource_manager.service_profiles
        assert 'communication' in resource_manager.service_profiles
        assert 'hardware' in resource_manager.service_profiles
        
        # Verify safety service is configured as critical
        safety_profile = resource_manager.service_profiles['safety']
        assert safety_profile.critical is True
        assert safety_profile.priority == 1  # Highest priority
    
    async def test_operation_mode_changes(self, resource_manager):
        """Test operation mode changes and resource adaptation"""
        # Test mode change to mowing
        await resource_manager.set_operation_mode(OperationMode.MOWING)
        assert resource_manager.current_mode == OperationMode.MOWING
        
        # Verify allocations changed for services with mode adjustments
        vision_allocation = resource_manager.current_allocations['vision']
        vision_profile = resource_manager.service_profiles['vision']
        mowing_limits = vision_profile.mode_adjustments[OperationMode.MOWING]
        
        assert vision_allocation.cpu_percent == mowing_limits.cpu_percent
        assert vision_allocation.memory_mb == mowing_limits.memory_mb
        
        # Test mode change to idle
        await resource_manager.set_operation_mode(OperationMode.IDLE)
        assert resource_manager.current_mode == OperationMode.IDLE
    
    async def test_high_cpu_pressure_response(self, resource_manager):
        """Test response to high CPU pressure"""
        # Simulate high CPU metrics
        high_cpu_metrics = MockMetrics.create_high_cpu_metrics()
        
        # Inject metrics and trigger adaptation
        resource_manager.metrics_history.append(high_cpu_metrics)
        resource_manager.last_adaptation_time = 0  # Force adaptation
        
        # Get initial allocations
        initial_allocations = {
            name: limits.cpu_percent 
            for name, limits in resource_manager.current_allocations.items()
        }
        
        # Trigger adaptation
        decisions = await resource_manager._analyze_and_adapt(high_cpu_metrics)
        await resource_manager._apply_allocation_decisions(decisions)
        
        # Verify non-critical services had CPU reduced
        non_critical_reduced = False
        for service_name, profile in resource_manager.service_profiles.items():
            if not profile.critical and profile.adaptive:
                current_cpu = resource_manager.current_allocations[service_name].cpu_percent
                initial_cpu = initial_allocations[service_name]
                if current_cpu < initial_cpu:
                    non_critical_reduced = True
                    break
        
        assert non_critical_reduced, "Non-critical services should have reduced CPU allocation"
        
        # Verify critical services maintained their allocation
        for service_name, profile in resource_manager.service_profiles.items():
            if profile.critical:
                current_cpu = resource_manager.current_allocations[service_name].cpu_percent
                initial_cpu = initial_allocations[service_name]
                assert current_cpu >= initial_cpu * 0.9, f"Critical service {service_name} allocation too low"
    
    async def test_memory_pressure_response(self, resource_manager):
        """Test response to high memory pressure"""
        # Simulate high memory metrics
        high_memory_metrics = MockMetrics.create_high_memory_metrics()
        
        # Inject metrics and trigger adaptation
        resource_manager.metrics_history.append(high_memory_metrics)
        resource_manager.last_adaptation_time = 0  # Force adaptation
        
        # Get initial allocations
        initial_allocations = {
            name: limits.memory_mb 
            for name, limits in resource_manager.current_allocations.items()
        }
        
        # Trigger adaptation
        decisions = await resource_manager._analyze_and_adapt(high_memory_metrics)
        await resource_manager._apply_allocation_decisions(decisions)
        
        # Verify non-critical services had memory reduced
        non_critical_reduced = False
        for service_name, profile in resource_manager.service_profiles.items():
            if not profile.critical and profile.adaptive:
                current_memory = resource_manager.current_allocations[service_name].memory_mb
                initial_memory = initial_allocations[service_name]
                if current_memory < initial_memory:
                    non_critical_reduced = True
                    break
        
        assert non_critical_reduced, "Non-critical services should have reduced memory allocation"
    
    async def test_resource_expansion_on_idle(self, resource_manager):
        """Test resource allocation expansion during low usage"""
        # Simulate low usage metrics
        low_usage_metrics = MockMetrics.create_low_usage_metrics()
        
        # Inject multiple low usage metrics to establish pattern
        for _ in range(10):
            resource_manager.metrics_history.append(low_usage_metrics)
        
        resource_manager.last_adaptation_time = 0  # Force adaptation
        
        # Get initial allocations
        initial_allocations = {
            name: limits.cpu_percent 
            for name, limits in resource_manager.current_allocations.items()
        }
        
        # Trigger adaptation
        decisions = await resource_manager._analyze_and_adapt(low_usage_metrics)
        await resource_manager._apply_allocation_decisions(decisions)
        
        # Verify some adaptive services had allocations increased
        allocations_increased = False
        for service_name, profile in resource_manager.service_profiles.items():
            if profile.adaptive:
                current_cpu = resource_manager.current_allocations[service_name].cpu_percent
                initial_cpu = initial_allocations[service_name]
                if current_cpu > initial_cpu:
                    allocations_increased = True
                    break
        
        assert allocations_increased, "Some services should have increased allocations during idle"
    
    async def test_performance_monitoring(self, resource_manager):
        """Test performance monitoring and metrics collection"""
        # Start monitoring
        assert resource_manager.monitoring_active
        
        # Wait for some metrics to be collected
        await asyncio.sleep(2)
        
        # Verify metrics are being collected
        assert len(resource_manager.metrics_history) > 0
        
        # Verify latest metrics are reasonable
        latest_metrics = list(resource_manager.metrics_history)[-1]
        assert 0 <= latest_metrics.cpu_percent <= 100
        assert 0 <= latest_metrics.memory_percent <= 100
        assert latest_metrics.timestamp is not None
    
    async def test_allocation_decision_tracking(self, resource_manager):
        """Test allocation decision tracking and history"""
        # Simulate adaptation scenario
        high_cpu_metrics = MockMetrics.create_high_cpu_metrics()
        resource_manager.last_adaptation_time = 0
        
        initial_history_length = len(resource_manager.allocation_history)
        
        # Trigger adaptation
        decisions = await resource_manager._analyze_and_adapt(high_cpu_metrics)
        await resource_manager._apply_allocation_decisions(decisions)
        
        # Verify decisions were recorded
        assert len(resource_manager.allocation_history) > initial_history_length
        
        # Verify decision structure
        if resource_manager.allocation_history:
            latest_decision = list(resource_manager.allocation_history)[-1]
            assert latest_decision.service_name is not None
            assert latest_decision.resource_type is not None
            assert latest_decision.reason is not None
            assert 0 <= latest_decision.confidence <= 1.0


@pytest.mark.asyncio
class TestPerformanceDashboard:
    """Test performance dashboard functionality"""
    
    async def test_dashboard_initialization(self, performance_dashboard):
        """Test dashboard initialization"""
        assert performance_dashboard.monitoring_active
        assert len(performance_dashboard.service_stats) > 0
        assert performance_dashboard.analyzer is not None
    
    async def test_efficiency_calculation(self, performance_dashboard):
        """Test efficiency score calculations"""
        # Add some test metrics
        test_metrics = [
            MockMetrics.create_high_cpu_metrics(),
            MockMetrics.create_low_usage_metrics(),
            MockMetrics.create_high_memory_metrics()
        ]
        
        for metrics in test_metrics:
            performance_dashboard.analyzer.add_metrics(metrics)
        
        # Calculate efficiency scores
        efficiency_scores = performance_dashboard.analyzer.calculate_efficiency_scores()
        
        # Verify scores are calculated
        assert 'cpu_efficiency' in efficiency_scores
        assert 'memory_efficiency' in efficiency_scores
        assert 'overall_efficiency' in efficiency_scores
        
        # Verify scores are in valid range
        for score in efficiency_scores.values():
            assert 0 <= score <= 100
    
    async def test_alert_generation(self, performance_dashboard):
        """Test performance alert generation"""
        # Simulate high CPU scenario
        high_cpu_metrics = MockMetrics.create_high_cpu_metrics()
        
        system_status = {
            'current_metrics': {
                'cpu_percent': high_cpu_metrics.cpu_percent,
                'memory_percent': high_cpu_metrics.memory_percent,
                'temperature': high_cpu_metrics.temperature
            }
        }
        
        efficiency_scores = {'overall_efficiency': 45.0}
        
        initial_alerts = len(performance_dashboard.active_alerts)
        
        # Check for alerts
        await performance_dashboard._check_alerts(system_status, efficiency_scores)
        
        # Verify alerts were generated
        assert len(performance_dashboard.active_alerts) > initial_alerts
        
        # Verify alert structure
        for alert in performance_dashboard.active_alerts.values():
            assert alert.level in ['info', 'warning', 'critical']
            assert alert.title is not None
            assert alert.message is not None
    
    async def test_service_performance_tracking(self, performance_dashboard):
        """Test service performance statistics tracking"""
        # Get initial service stats
        initial_stats = dict(performance_dashboard.service_stats)
        
        # Simulate system status update
        system_status = {
            'service_allocations': {
                'vision': {'cpu_percent': 45.0, 'memory_mb': 2048.0},
                'safety': {'cpu_percent': 25.0, 'memory_mb': 512.0}
            }
        }
        
        await performance_dashboard._update_service_stats(system_status)
        
        # Verify stats were updated
        for service_name in system_status['service_allocations']:
            stats = performance_dashboard.service_stats[service_name]
            assert stats.last_updated > initial_stats[service_name].last_updated
    
    async def test_dashboard_data_export(self, performance_dashboard):
        """Test dashboard data export functionality"""
        # Add some test data
        test_metrics = MockMetrics.create_low_usage_metrics()
        performance_dashboard.analyzer.add_metrics(test_metrics)
        
        # Wait for dashboard update
        await asyncio.sleep(1)
        
        # Get dashboard data
        dashboard_data = await performance_dashboard.get_dashboard_data()
        
        # Verify data structure
        assert 'timestamp' in dashboard_data
        assert 'system_overview' in dashboard_data
        assert 'efficiency_metrics' in dashboard_data
        assert 'service_performance' in dashboard_data
        
        # Verify system overview
        overview = dashboard_data['system_overview']
        assert 'monitoring_active' in overview
        assert 'total_services' in overview
        assert 'system_stability' in overview


@pytest.mark.asyncio
class TestEnhancedSystemMonitor:
    """Test enhanced system monitor functionality"""
    
    async def test_monitor_initialization(self, enhanced_monitor):
        """Test enhanced monitor initialization"""
        assert enhanced_monitor.monitoring_active
        assert enhanced_monitor.resource_manager is not None
        assert enhanced_monitor.dashboard is not None
        assert enhanced_monitor.predictive_analyzer is not None
        assert enhanced_monitor.automation_engine is not None
    
    async def test_predictive_analytics(self, enhanced_monitor):
        """Test predictive analytics functionality"""
        # Add historical metrics for prediction
        base_time = datetime.now()
        for i in range(50):
            metrics = ResourceMetrics(
                timestamp=base_time + timedelta(minutes=i),
                cpu_percent=50.0 + np.sin(i * 0.1) * 10,  # Oscillating pattern
                memory_percent=60.0 + i * 0.2,  # Increasing trend
                memory_mb=9830.4 + i * 10,
                io_read_mb_s=5.0,
                io_write_mb_s=3.0,
                network_bytes_s=1024000,
                load_average=[1.5, 1.5, 1.5],
                temperature=60.0 + i * 0.1
            )
            enhanced_monitor.predictive_analyzer.add_metrics(metrics)
        
        # Test predictions
        cpu_prediction = enhanced_monitor.predictive_analyzer.predict_resource_usage('cpu_percent', 30)
        memory_prediction = enhanced_monitor.predictive_analyzer.predict_resource_usage('memory_percent', 30)
        
        # Verify predictions were generated
        assert cpu_prediction is not None
        assert memory_prediction is not None
        
        # Verify prediction structure
        assert cpu_prediction.metric_name == 'cpu_percent'
        assert cpu_prediction.predicted_value is not None
        assert 0 <= cpu_prediction.confidence <= 1.0
        assert len(cpu_prediction.factors) > 0
    
    async def test_automation_rules(self, enhanced_monitor):
        """Test automation rule evaluation and execution"""
        # Get automation engine
        automation_engine = enhanced_monitor.automation_engine
        
        # Verify default rules are loaded
        assert len(automation_engine.rules) > 0
        assert 'high_cpu_pressure' in automation_engine.rules
        assert 'memory_pressure' in automation_engine.rules
        
        # Test rule evaluation with high CPU
        high_cpu_metrics = MockMetrics.create_high_cpu_metrics()
        efficiency_scores = {'overall_efficiency': 45.0}
        
        # Evaluate rules
        triggered_actions = await automation_engine.evaluate_rules(high_cpu_metrics, efficiency_scores)
        
        # Verify actions were triggered for high CPU
        assert len(triggered_actions) > 0
        
        # Verify rule history was updated
        assert len(automation_engine.rule_history) > 0
    
    async def test_optimization_suggestions(self, enhanced_monitor):
        """Test optimization suggestion generation"""
        # Simulate poor performance metrics
        poor_metrics = ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=95.0,
            memory_percent=90.0,
            memory_mb=14745.6,
            io_read_mb_s=50.0,
            io_write_mb_s=40.0,
            network_bytes_s=5120000,
            load_average=[4.5, 4.2, 4.0],
            temperature=85.0
        )
        
        poor_efficiency = {
            'overall_efficiency': 35.0,
            'cpu_efficiency': 25.0,
            'memory_efficiency': 45.0
        }
        
        initial_suggestions = len(enhanced_monitor.optimization_suggestions)
        
        # Trigger optimization check
        await enhanced_monitor._check_optimization_opportunities(poor_metrics, poor_efficiency)
        
        # Verify suggestions were generated
        assert len(enhanced_monitor.optimization_suggestions) > initial_suggestions
        
        # Verify suggestion structure
        if enhanced_monitor.optimization_suggestions:
            suggestion = list(enhanced_monitor.optimization_suggestions)[-1]
            assert suggestion.title is not None
            assert suggestion.description is not None
            assert suggestion.category in ['performance', 'stability', 'efficiency']
            assert 0 <= suggestion.impact_score <= 100
            assert suggestion.difficulty in ['easy', 'medium', 'hard']
    
    async def test_comprehensive_status(self, enhanced_monitor):
        """Test comprehensive status reporting"""
        # Add some test data
        test_metrics = MockMetrics.create_low_usage_metrics()
        enhanced_monitor.predictive_analyzer.add_metrics(test_metrics)
        
        # Wait for some processing
        await asyncio.sleep(2)
        
        # Get comprehensive status
        status = await enhanced_monitor.get_comprehensive_status()
        
        # Verify status structure
        assert 'system_overview' in status
        assert 'predictions' in status
        assert 'automation' in status
        assert 'optimization_suggestions' in status
        assert 'enhanced_monitoring' in status
        
        # Verify automation status
        automation = status['automation']
        assert 'rules_enabled' in automation
        assert 'total_rules' in automation
        assert 'rules' in automation


@pytest.mark.asyncio
class TestPerformanceBenchmarks:
    """Performance benchmarking tests"""
    
    async def test_resource_allocation_speed(self, resource_manager):
        """Benchmark resource allocation decision speed"""
        test_metrics = MockMetrics.create_high_cpu_metrics()
        
        # Benchmark allocation decision time
        start_time = time.time()
        
        for _ in range(100):
            decisions = await resource_manager._analyze_and_adapt(test_metrics)
            
        end_time = time.time()
        avg_decision_time = (end_time - start_time) / 100
        
        # Allocation decisions should be fast (< 50ms average)
        assert avg_decision_time < 0.05, f"Decision time too slow: {avg_decision_time:.3f}s"
    
    async def test_monitoring_overhead(self, resource_manager):
        """Benchmark monitoring overhead"""
        # Measure system resources before monitoring
        process = psutil.Process()
        initial_cpu = process.cpu_percent()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Wait for monitoring to settle
        await asyncio.sleep(5)
        
        # Measure resources after monitoring
        final_cpu = process.cpu_percent()
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        cpu_overhead = final_cpu - initial_cpu
        memory_overhead = final_memory - initial_memory
        
        # Monitoring overhead should be minimal
        assert cpu_overhead < 10.0, f"CPU overhead too high: {cpu_overhead:.1f}%"
        assert memory_overhead < 50.0, f"Memory overhead too high: {memory_overhead:.1f}MB"
    
    async def test_dashboard_response_time(self, performance_dashboard):
        """Benchmark dashboard data retrieval speed"""
        # Add test data
        for _ in range(100):
            test_metrics = MockMetrics.create_low_usage_metrics()
            performance_dashboard.analyzer.add_metrics(test_metrics)
        
        # Benchmark dashboard data retrieval
        start_time = time.time()
        
        for _ in range(50):
            dashboard_data = await performance_dashboard.get_dashboard_data()
            
        end_time = time.time()
        avg_response_time = (end_time - start_time) / 50
        
        # Dashboard response should be fast (< 100ms average)
        assert avg_response_time < 0.1, f"Dashboard response too slow: {avg_response_time:.3f}s"
    
    async def test_prediction_accuracy(self, enhanced_monitor):
        """Test prediction accuracy over time"""
        # Generate synthetic data with known pattern
        base_time = datetime.now()
        test_pattern = []
        
        for i in range(100):
            # Create predictable sine wave pattern
            cpu_value = 50.0 + 20.0 * np.sin(i * 0.1)
            metrics = ResourceMetrics(
                timestamp=base_time + timedelta(minutes=i),
                cpu_percent=cpu_value,
                memory_percent=60.0,
                memory_mb=9830.4,
                io_read_mb_s=5.0,
                io_write_mb_s=3.0,
                network_bytes_s=1024000,
                load_average=[1.5, 1.5, 1.5],
                temperature=65.0
            )
            enhanced_monitor.predictive_analyzer.add_metrics(metrics)
            test_pattern.append(cpu_value)
        
        # Test predictions at different horizons
        prediction_errors = []
        
        for horizon in [15, 30, 60]:
            prediction = enhanced_monitor.predictive_analyzer.predict_resource_usage('cpu_percent', horizon)
            if prediction:
                # Calculate actual value at prediction horizon
                future_index = min(len(test_pattern) - 1, 80 + horizon // 5)  # Approximate future index
                actual_future_value = test_pattern[future_index]
                
                error = abs(prediction.predicted_value - actual_future_value)
                prediction_errors.append(error)
        
        if prediction_errors:
            avg_error = np.mean(prediction_errors)
            # Prediction error should be reasonable (< 15% on average)
            assert avg_error < 15.0, f"Prediction error too high: {avg_error:.1f}%"


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """Integration test scenarios"""
    
    async def test_mowing_mode_performance_optimization(self, enhanced_monitor):
        """Test full system performance during mowing mode"""
        # Set to mowing mode
        await enhanced_monitor.set_operation_mode(OperationMode.MOWING)
        
        # Simulate mowing workload
        mowing_metrics = ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=75.0,
            memory_percent=70.0,
            memory_mb=11468.8,
            io_read_mb_s=25.0,
            io_write_mb_s=20.0,
            network_bytes_s=2048000,
            load_average=[3.0, 2.8, 2.5],
            temperature=72.0
        )
        
        # Add metrics and wait for adaptation
        enhanced_monitor.predictive_analyzer.add_metrics(mowing_metrics)
        await asyncio.sleep(2)
        
        # Get system status
        status = await enhanced_monitor.get_comprehensive_status()
        
        # Verify mowing mode adaptations
        assert status['system_overview']['operation_mode'] == 'mowing'
        
        # Verify vision and sensor fusion services got increased allocations
        resource_status = status.get('resource_utilization', {})
        service_allocations = resource_status.get('service_allocations', {})
        
        if 'vision' in service_allocations:
            vision_cpu = service_allocations['vision']['cpu_percent']
            assert vision_cpu >= 40.0, "Vision service should have high CPU allocation in mowing mode"
    
    async def test_emergency_thermal_management(self, enhanced_monitor):
        """Test emergency thermal management scenario"""
        # Simulate high temperature scenario
        hot_metrics = ResourceMetrics(
            timestamp=datetime.now(),
            cpu_percent=60.0,
            memory_percent=50.0,
            memory_mb=8192.0,
            io_read_mb_s=10.0,
            io_write_mb_s=8.0,
            network_bytes_s=1024000,
            load_average=[2.0, 2.0, 2.0],
            temperature=82.0  # Critical temperature
        )
        
        # Add hot metrics
        enhanced_monitor.predictive_analyzer.add_metrics(hot_metrics)
        
        # Trigger automation evaluation
        automation_engine = enhanced_monitor.automation_engine
        efficiency_scores = {'overall_efficiency': 70.0}
        
        actions = await automation_engine.evaluate_rules(hot_metrics, efficiency_scores)
        
        # Verify thermal management actions were taken
        thermal_action_taken = any('thermal' in action.lower() or 'temperature' in action.lower() 
                                 for action in actions)
        
        # Should either take thermal action or switch to idle mode
        assert thermal_action_taken or enhanced_monitor.resource_manager.current_mode == OperationMode.IDLE
    
    async def test_long_term_stability(self, enhanced_monitor):
        """Test long-term system stability with varying loads"""
        # Simulate 24 hours of operation with varying loads
        base_time = datetime.now()
        
        for hour in range(24):
            # Create realistic daily usage pattern
            if 6 <= hour <= 20:  # Daytime - higher activity
                cpu_base = 60.0
                memory_base = 65.0
            else:  # Nighttime - lower activity
                cpu_base = 30.0
                memory_base = 45.0
            
            # Add some randomness
            cpu_variation = np.random.normal(0, 10)
            memory_variation = np.random.normal(0, 8)
            
            metrics = ResourceMetrics(
                timestamp=base_time + timedelta(hours=hour),
                cpu_percent=max(10, min(95, cpu_base + cpu_variation)),
                memory_percent=max(20, min(90, memory_base + memory_variation)),
                memory_mb=8192.0 + memory_variation * 100,
                io_read_mb_s=5.0 + hour * 0.5,
                io_write_mb_s=3.0 + hour * 0.3,
                network_bytes_s=1024000 + hour * 50000,
                load_average=[1.5, 1.5, 1.5],
                temperature=55.0 + hour * 0.5
            )
            
            enhanced_monitor.predictive_analyzer.add_metrics(metrics)
        
        # Calculate stability metrics
        status = await enhanced_monitor.get_comprehensive_status()
        
        # Verify system remained stable
        system_overview = status['system_overview']
        stability_score = system_overview.get('system_stability', 0)
        
        # System should maintain reasonable stability over 24 hours
        assert stability_score >= 60.0, f"Long-term stability too low: {stability_score:.1f}"
        
        # Verify automation didn't trigger excessively
        automation = status['automation']
        total_triggers = sum(rule['trigger_count'] for rule in automation['rules'].values())
        
        # Should not have excessive automation triggers (max ~1 per hour)
        assert total_triggers <= 30, f"Too many automation triggers: {total_triggers}"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
