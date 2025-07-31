#!/usr/bin/env python3
"""
Validation script for deployment automation system
Tests core functionality of deployment, build, fleet, and monitoring systems
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from system_integration.config_manager import ConfigManager
from system_integration.deployment_manager import DeploymentManager, DeploymentPackage, DeploymentType
from system_integration.build_system import BuildSystem, BuildConfig
from system_integration.fleet_manager import FleetManager
from system_integration.system_monitor import SystemMonitor
from system_integration.health_monitor import HealthMonitor
from system_integration.state_machine import SystemStateMachine


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def validate_config_manager():
    """Test configuration manager"""
    logger.info("Testing Configuration Manager...")
    
    try:
        config_manager = ConfigManager()
        await config_manager.load_all_configs()
        
        # Test loading deployment config
        deployment_config = config_manager.get_config('deployment')
        assert deployment_config is not None, "Deployment config not loaded"
        
        # Test loading build config
        build_config = config_manager.get_config('build')
        assert build_config is not None, "Build config not loaded"
        
        # Test loading fleet config
        fleet_config = config_manager.get_config('fleet')
        assert fleet_config is not None, "Fleet config not loaded"
        
        logger.info("✓ Configuration Manager validation passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Configuration Manager validation failed: {e}")
        return False


async def validate_deployment_manager():
    """Test deployment manager"""
    logger.info("Testing Deployment Manager...")
    
    try:
        config_manager = ConfigManager()
        await config_manager.load_all_configs()
        
        health_monitor = HealthMonitor()
        state_machine = SystemStateMachine()
        
        deployment_manager = DeploymentManager(config_manager, health_monitor, state_machine)
        await deployment_manager.initialize()
        
        # Test getting deployment status
        status = await deployment_manager.get_deployment_status()
        assert isinstance(status, dict), "Deployment status should be a dict"
        assert 'active_version' in status, "Status should include active version"
        
        await deployment_manager.shutdown()
        
        logger.info("✓ Deployment Manager validation passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Deployment Manager validation failed: {e}")
        return False


async def validate_build_system():
    """Test build system"""
    logger.info("Testing Build System...")
    
    try:
        config_manager = ConfigManager()
        await config_manager.load_all_configs()
        
        build_system = BuildSystem(config_manager)
        await build_system.initialize()
        
        # Test build configuration
        build_config = BuildConfig(
            version="test-1.0.0",
            build_type="debug",
            include_tests=False,
            include_docs=False,
            compression_level=1,
            sign_package=False,
            run_tests=False,
            validate_config=False
        )
        
        # Note: We won't actually run a build as it requires the full source tree
        # Just test that the build system initializes properly
        
        logger.info("✓ Build System validation passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Build System validation failed: {e}")
        return False


async def validate_fleet_manager():
    """Test fleet manager"""
    logger.info("Testing Fleet Manager...")
    
    try:
        config_manager = ConfigManager()
        await config_manager.load_all_configs()
        
        fleet_manager = FleetManager(config_manager)
        await fleet_manager.initialize()
        
        # Test getting fleet status
        status = await fleet_manager.get_fleet_status()
        assert isinstance(status, dict), "Fleet status should be a dict"
        
        await fleet_manager.shutdown()
        
        logger.info("✓ Fleet Manager validation passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Fleet Manager validation failed: {e}")
        return False


async def validate_system_monitor():
    """Test system monitor"""
    logger.info("Testing System Monitor...")
    
    try:
        config_manager = ConfigManager()
        await config_manager.load_all_configs()
        
        system_monitor = SystemMonitor(config_manager)
        await system_monitor.initialize()
        
        # Test getting system status
        status = await system_monitor.get_system_status()
        assert isinstance(status, dict), "System status should be a dict"
        
        await system_monitor.shutdown()
        
        logger.info("✓ System Monitor validation passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ System Monitor validation failed: {e}")
        return False


async def validate_integration():
    """Test system integration"""
    logger.info("Testing System Integration...")
    
    try:
        config_manager = ConfigManager()
        await config_manager.load_all_configs()
        
        # Test that all components can be initialized together
        health_monitor = HealthMonitor()
        state_machine = SystemStateMachine()
        
        deployment_manager = DeploymentManager(config_manager, health_monitor, state_machine)
        build_system = BuildSystem(config_manager)
        fleet_manager = FleetManager(config_manager)
        system_monitor = SystemMonitor(config_manager)
        
        # Initialize all components
        await system_monitor.initialize()
        await deployment_manager.initialize()
        await build_system.initialize()
        await fleet_manager.initialize()
        
        # Test that they can get status from each other
        deployment_status = await deployment_manager.get_deployment_status()
        fleet_status = await fleet_manager.get_fleet_status()
        monitor_status = await system_monitor.get_system_status()
        
        # Shutdown all components
        await fleet_manager.shutdown()
        await deployment_manager.shutdown()
        await system_monitor.shutdown()
        
        logger.info("✓ System Integration validation passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ System Integration validation failed: {e}")
        return False


async def main():
    """Run all validation tests"""
    logger.info("Starting Deployment Automation System Validation")
    logger.info("=" * 60)
    
    tests = [
        validate_config_manager,
        validate_deployment_manager,
        validate_build_system,
        validate_fleet_manager,
        validate_system_monitor,
        validate_integration
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if await test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Test {test.__name__} crashed: {e}")
            failed += 1
        
        print()  # Add spacing between tests
    
    logger.info("=" * 60)
    logger.info(f"Validation Summary: {passed} passed, {failed} failed")
    
    if failed == 0:
        logger.info("🎉 All deployment automation components validated successfully!")
        return 0
    else:
        logger.error(f"❌ {failed} validation(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
