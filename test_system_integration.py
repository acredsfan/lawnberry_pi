#!/usr/bin/env python3
"""
Comprehensive System Integration Test Suite
Tests system startup, service orchestration, health monitoring, and shutdown
"""

import asyncio
import logging
import subprocess
import time
import json
import tempfile
from pathlib import Path
from typing import Dict, List

# Setup test logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SystemIntegrationTest:
    """System integration test suite"""
    
    def __init__(self):
        self.test_results: Dict[str, bool] = {}
        self.services_to_test = [
            'communication', 'data_management', 'hardware',
            'sensor_fusion', 'weather', 'power_management',
            'safety', 'vision', 'web_api'
        ]
    
    async def run_all_tests(self):
        """Run all system integration tests"""
        logger.info("Starting System Integration Test Suite")
        
        tests = [
            self.test_config_loading,
            self.test_service_orchestrator,
            self.test_health_monitor,
            self.test_state_machine,
            self.test_service_dependencies,
            self.test_failure_recovery,
            self.test_graceful_shutdown,
            self.test_system_persistence
        ]
        
        for test in tests:
            test_name = test.__name__
            logger.info(f"Running test: {test_name}")
            
            try:
                await test()
                self.test_results[test_name] = True
                logger.info(f"✓ {test_name} PASSED")
            except Exception as e:
                self.test_results[test_name] = False
                logger.error(f"✗ {test_name} FAILED: {e}")
        
        # Print results summary
        self.print_test_summary()
        
        # Return overall success
        return all(self.test_results.values())
    
    async def test_config_loading(self):
        """Test configuration management"""
        from src.system_integration.config_manager import ConfigManager
        
        config_manager = ConfigManager('config')
        
        # Test loading all configs
        await config_manager.load_all_configs()
        
        # Verify system config exists
        system_config = config_manager.get_system_config()
        assert system_config is not None, "System config not loaded"
        assert 'system' in system_config, "System section missing"
        assert 'services' in system_config, "Services section missing"
        
        # Test service config retrieval
        comm_config = config_manager.get_service_config('communication')
        assert comm_config is not None, "Communication service config not found"
        
        # Test config validation
        status = config_manager.get_config_status()
        for config_name, config_status in status.items():
            assert config_status['validated'], f"Config {config_name} not validated"
        
        await config_manager.shutdown()
        logger.info("Configuration loading test completed")
    
    async def test_service_orchestrator(self):
        """Test service orchestration"""
        from src.system_integration.service_orchestrator import ServiceOrchestrator
        from src.system_integration.config_manager import ConfigManager
        
        config_manager = ConfigManager('config')
        await config_manager.load_all_configs()
        
        orchestrator = ServiceOrchestrator()
        await orchestrator.initialize(config_manager.get_system_config())
        
        # Test service existence checks
        for service_name in self.services_to_test:
            has_service = await orchestrator.has_service(service_name)
            if service_name in ['communication', 'data_management', 'hardware', 'safety']:
                assert has_service, f"Critical service {service_name} not found"
        
        # Test dependency graph
        assert orchestrator.dependency_graph is not None, "Dependency graph not built"
        
        # Test service status retrieval
        status = orchestrator.get_all_service_status()
        assert isinstance(status, dict), "Service status not returned as dict"
        
        await config_manager.shutdown()
        logger.info("Service orchestrator test completed")
    
    async def test_health_monitor(self):
        """Test health monitoring system"""
        from src.system_integration.health_monitor import HealthMonitor
        
        health_monitor = HealthMonitor()
        await health_monitor.initialize()
        
        # Test system health retrieval
        system_health = await health_monitor.get_system_health()
        assert system_health is not None, "System health not retrieved"
        assert hasattr(system_health, 'is_healthy'), "Health status missing"
        assert hasattr(system_health, 'service_health'), "Service health missing"
        assert hasattr(system_health, 'resource_usage'), "Resource usage missing"
        
        # Test service health checking
        for service_name in ['communication', 'safety']:
            service_health = health_monitor.get_service_health(service_name)
            assert service_health is not None, f"Service health for {service_name} not found"
        
        # Test resource monitoring
        resource_history = health_monitor.get_resource_history(1)
        assert isinstance(resource_history, list), "Resource history not a list"
        
        await health_monitor.shutdown()
        logger.info("Health monitor test completed")
    
    async def test_state_machine(self):
        """Test system state machine"""
        from src.system_integration.state_machine import SystemStateMachine, SystemState
        
        state_machine = SystemStateMachine()
        await state_machine.initialize()
        
        # Test initial state
        assert state_machine.current_state in [SystemState.INITIALIZING, SystemState.ERROR], \
            f"Unexpected initial state: {state_machine.current_state}"
        
        # Test valid transitions
        valid_transitions = state_machine.get_valid_transitions()
        assert isinstance(valid_transitions, list), "Valid transitions not returned as list"
        assert len(valid_transitions) > 0, "No valid transitions found"
        
        # Test transition validation
        if state_machine.current_state == SystemState.INITIALIZING:
            can_start = state_machine.can_transition_to(SystemState.STARTING)
            assert can_start, "Cannot transition to STARTING from INITIALIZING"
            
            # Test actual transition
            success = await state_machine.transition_to(SystemState.STARTING, "Test transition")
            assert success, "Failed to transition to STARTING"
            assert state_machine.current_state == SystemState.STARTING, "State not updated"
        
        # Test state persistence
        await state_machine.save_state()
        
        # Test state summary
        summary = state_machine.get_state_summary()
        assert 'current_state' in summary, "State summary missing current_state"
        assert 'valid_transitions' in summary, "State summary missing valid_transitions"
        
        await state_machine.shutdown()
        logger.info("State machine test completed")
    
    async def test_service_dependencies(self):
        """Test service dependency handling"""
        from src.system_integration.service_orchestrator import ServiceOrchestrator
        from src.system_integration.config_manager import ConfigManager
        
        config_manager = ConfigManager('config')
        await config_manager.load_all_configs()
        
        orchestrator = ServiceOrchestrator()
        await orchestrator.initialize(config_manager.get_system_config())
        
        # Test dependency graph
        deps = orchestrator.dependency_graph
        
        # Verify critical dependencies
        if 'hardware' in deps:
            hardware_deps = deps['hardware']
            assert 'communication' in hardware_deps, "Hardware should depend on communication"
        
        if 'safety' in deps:
            safety_deps = deps['safety']
            assert 'hardware' in safety_deps, "Safety should depend on hardware"
        
        # Test reverse dependencies
        reverse_deps = orchestrator.reverse_dependencies
        if 'communication' in reverse_deps:
            comm_dependents = reverse_deps['communication']
            assert len(comm_dependents) > 0, "Communication should have dependents"
        
        await config_manager.shutdown()
        logger.info("Service dependencies test completed")
    
    async def test_failure_recovery(self):
        """Test failure handling and recovery"""
        from src.system_integration.health_monitor import HealthMonitor
        
        health_monitor = HealthMonitor()
        await health_monitor.initialize()
        
        # Test circuit breaker functionality
        circuit_breakers = health_monitor.circuit_breakers
        assert isinstance(circuit_breakers, dict), "Circuit breakers not initialized"
        
        # Test alert threshold handling
        thresholds = health_monitor.alert_thresholds
        assert 'cpu_percent' in thresholds, "CPU threshold not set"
        assert 'memory_percent' in thresholds, "Memory threshold not set"
        
        # Test threshold updates
        new_thresholds = {'cpu_percent': 95.0}
        health_monitor.update_alert_thresholds(new_thresholds)
        assert health_monitor.alert_thresholds['cpu_percent'] == 95.0, "Threshold not updated"
        
        await health_monitor.shutdown()
        logger.info("Failure recovery test completed")
    
    async def test_graceful_shutdown(self):
        """Test graceful shutdown procedures"""
        from src.system_integration.system_manager import SystemManager
        
        # This test verifies shutdown logic without actually shutting down
        system_manager = SystemManager()
        
        # Test shutdown event setup
        assert hasattr(system_manager, 'shutdown_event'), "Shutdown event not initialized"
        assert hasattr(system_manager, 'running'), "Running flag not initialized"
        
        # Test signal handler setup (verify it exists)
        assert hasattr(system_manager, '_setup_signal_handlers'), "Signal handlers not implemented"
        
        logger.info("Graceful shutdown test completed")
    
    async def test_system_persistence(self):
        """Test system state and configuration persistence"""
        from src.system_integration.state_machine import SystemStateMachine
        from src.system_integration.config_manager import ConfigManager
        
        # Test state persistence
        with tempfile.TemporaryDirectory() as temp_dir:
            # Override state file location for testing
            state_machine = SystemStateMachine()
            state_machine.state_file = Path(temp_dir) / 'test_state.json'
            
            await state_machine.initialize()
            await state_machine.save_state()
            
            # Verify state file exists
            assert state_machine.state_file.exists(), "State file not created"
            
            # Load state in new instance
            new_state_machine = SystemStateMachine()
            new_state_machine.state_file = state_machine.state_file
            await new_state_machine._load_state()
            
            assert new_state_machine.current_state == state_machine.current_state, \
                "State not preserved across reload"
        
        # Test config backup
        config_manager = ConfigManager('config')
        await config_manager.load_all_configs()
        
        # Test backup creation
        if 'system.yaml' in config_manager.configs:
            await config_manager._backup_config('system.yaml')
            
            # Verify backup exists
            backup_files = list(config_manager.backup_dir.glob('system.yaml.*.backup'))
            assert len(backup_files) > 0, "Config backup not created"
        
        await config_manager.shutdown()
        logger.info("System persistence test completed")
    
    def print_test_summary(self):
        """Print test results summary"""
        logger.info("\n" + "="*50)
        logger.info("SYSTEM INTEGRATION TEST RESULTS")
        logger.info("="*50)
        
        passed = sum(1 for result in self.test_results.values() if result)
        total = len(self.test_results)
        
        for test_name, result in self.test_results.items():
            status = "PASS" if result else "FAIL"
            logger.info(f"{test_name:<30} {status}")
        
        logger.info("-"*50)
        logger.info(f"Total: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 ALL TESTS PASSED!")
        else:
            logger.error(f"❌ {total - passed} TESTS FAILED!")
        
        logger.info("="*50)


async def main():
    """Main test runner"""
    test_suite = SystemIntegrationTest()
    success = await test_suite.run_all_tests()
    
    if not success:
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
