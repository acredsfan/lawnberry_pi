"""
Data Management System Demo
Demonstrates comprehensive data management capabilities
"""

import asyncio
import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.data_management import DataManager
from src.data_management.models import SensorReading, OperationalState, ConfigurationData
from src.data_management.state_manager import SystemState, OperationMode


async def setup_logging():
    """Setup logging for demo"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


async def load_demo_config():
    """Load demo configuration"""
    config_path = Path(__file__).parent.parent / "config" / "data_management.yaml"
    
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        # Fallback demo config
        config = {
            'redis': {
                'host': 'localhost',
                'port': 6379,
                'db': 0
            },
            'database_path': '/tmp/lawnberry_demo.db',
            'backup_path': '/tmp/lawnberry_backups'
        }
    
    return config


async def demonstrate_sensor_data_operations(dm: DataManager, logger):
    """Demonstrate high-performance sensor data operations"""
    logger.info("=== Sensor Data Operations Demo ===")
    
    # Create sample sensor readings
    sensors = [
        ("gps_primary", "gps", {"lat": 40.7128, "lng": -74.0060, "accuracy": 2.5}),
        ("battery_main", "battery", {"voltage": 12.6, "current": -3.2, "temperature": 28.5}),
        ("imu_bno085", "imu", {"heading": 135.0, "pitch": 1.2, "roll": -0.8}),
        ("camera_rpi", "camera", {"objects_detected": 2, "confidence": 0.95}),
        ("tof_front_left", "tof", {"distance_mm": 1250, "signal_strength": 8}),
        ("tof_front_right", "tof", {"distance_mm": 1180, "signal_strength": 9}),
        ("bme280", "environmental", {"temperature": 22.5, "humidity": 65.2, "pressure": 1013.2})
    ]
    
    # Store sensor readings and measure performance
    logger.info("Storing sensor readings...")
    start_time = asyncio.get_event_loop().time()
    
    for sensor_id, sensor_type, value in sensors:
        reading = SensorReading(
            sensor_id=sensor_id,
            sensor_type=sensor_type,
            timestamp=datetime.now(),
            value=value,
            unit="mixed" if isinstance(value, dict) else "raw",
            quality=0.95,
            metadata={"demo": True, "batch": "initial"}
        )
        
        success = await dm.store_sensor_reading(reading)
        if success:
            logger.info(f"✓ Stored {sensor_type} reading from {sensor_id}")
        else:
            logger.error(f"✗ Failed to store {sensor_type} reading")
    
    storage_time = (asyncio.get_event_loop().time() - start_time) * 1000
    logger.info(f"Stored {len(sensors)} readings in {storage_time:.2f}ms")
    
    # Demonstrate fast retrieval
    logger.info("\nRetrieving sensor data...")
    start_time = asyncio.get_event_loop().time()
    
    # Get recent GPS readings
    gps_readings = await dm.get_sensor_readings(sensor_type="gps", limit=10)
    
    # Get battery data
    battery_readings = await dm.get_sensor_readings(sensor_id="battery_main", limit=5)
    
    retrieval_time = (asyncio.get_event_loop().time() - start_time) * 1000
    logger.info(f"Retrieved data in {retrieval_time:.2f}ms")
    logger.info(f"Found {len(gps_readings)} GPS readings, {len(battery_readings)} battery readings")
    
    # Demonstrate time-based queries
    logger.info("\nTime-based sensor queries...")
    recent_time = datetime.now() - timedelta(minutes=5)
    recent_readings = await dm.get_sensor_readings(start_time=recent_time)
    logger.info(f"Found {len(recent_readings)} readings from last 5 minutes")


async def demonstrate_state_management(dm: DataManager, logger):
    """Demonstrate operational state management and persistence"""
    logger.info("\n=== State Management Demo ===")
    
    # Get initial state
    initial_state = await dm.get_current_state()
    logger.info(f"Initial state: {initial_state.state} (Battery: {initial_state.battery_level}%)")
    
    # Simulate mowing operation sequence
    logger.info("\nSimulating mowing operation sequence...")
    
    # Start mowing
    await dm.update_system_state(
        new_state=SystemState.MOWING.value,
        mode=OperationMode.AUTOMATIC.value,
        battery_level=95.0,
        current_task="mowing_front_yard",
        progress=0.0
    )
    logger.info("✓ Started mowing operation")
    
    # Simulate progress updates
    for progress in [0.25, 0.5, 0.75]:
        battery_level = 95.0 - (progress * 20)  # Battery drains during mowing
        await dm.update_system_state(
            progress=progress,
            battery_level=battery_level
        )
        logger.info(f"✓ Progress: {progress*100:.0f}%, Battery: {battery_level:.1f}%")
        await asyncio.sleep(1)  # Simulate time passing
    
    # Complete mowing and return to charging
    await dm.update_system_state(
        new_state=SystemState.CHARGING.value,
        current_task="returning_to_dock",
        progress=1.0,
        battery_level=75.0
    )
    logger.info("✓ Completed mowing, returning to charge")
    
    # Get final state
    final_state = await dm.get_current_state()
    logger.info(f"Final state: {final_state.state} (Task: {final_state.current_task})")
    
    # Demonstrate recovery data
    logger.info("\nDemonstrating session recovery...")
    await dm.state.set_recovery_data("last_mowing_area", "front_yard")
    await dm.state.set_recovery_data("mowing_pattern", "parallel_lines")
    
    recovery_area = await dm.state.get_recovery_data("last_mowing_area")
    recovery_pattern = await dm.state.get_recovery_data("mowing_pattern")
    logger.info(f"Recovery data - Area: {recovery_area}, Pattern: {recovery_pattern}")
    
    # Demonstrate checkpoint creation
    checkpoint_created = await dm.state.create_checkpoint("mowing_complete")
    if checkpoint_created:
        logger.info("✓ Created state checkpoint 'mowing_complete'")


async def demonstrate_configuration_management(dm: DataManager, logger):
    """Demonstrate configuration management with caching"""
    logger.info("\n=== Configuration Management Demo ===")
    
    # Set various configuration parameters
    configs = [
        ("navigation", "max_speed", 1.5, "float", {"unit": "m/s", "range": "0.5-2.0"}),
        ("safety", "emergency_stop_distance", 0.5, "float", {"unit": "m", "critical": True}),
        ("mowing", "cutting_height", 25, "int", {"unit": "mm", "range": "15-50"}),
        ("battery", "low_battery_threshold", 20.0, "float", {"unit": "%", "warning_level": True}),
        ("system", "log_level", "INFO", "str", {"options": ["DEBUG", "INFO", "WARNING", "ERROR"]}),
        ("weather", "rain_threshold", 80.0, "float", {"unit": "%", "humidity_based": True})
    ]
    
    logger.info("Setting configuration parameters...")
    for section, key, value, data_type, metadata in configs:
        success = await dm.set_configuration(section, key, value, data_type, metadata)
        if success:
            logger.info(f"✓ Set {section}.{key} = {value}")
        else:
            logger.error(f"✗ Failed to set {section}.{key}")
    
    # Demonstrate fast configuration retrieval
    logger.info("\nRetrieving configurations...")
    start_time = asyncio.get_event_loop().time()
    
    # Get specific configuration values
    max_speed = await dm.get_configuration("navigation", "max_speed")
    stop_distance = await dm.get_configuration("safety", "emergency_stop_distance")
    
    retrieval_time = (asyncio.get_event_loop().time() - start_time) * 1000
    logger.info(f"Retrieved configs in {retrieval_time:.2f}ms")
    logger.info(f"Max speed: {max_speed} m/s, Stop distance: {stop_distance} m")
    
    # Get all navigation configurations
    nav_configs = await dm.get_configuration("navigation")
    logger.info(f"Navigation section has {len(nav_configs)} parameters")
    
    for config in nav_configs:
        logger.info(f"  {config.key}: {config.value} ({config.data_type})")


async def demonstrate_analytics_and_reporting(dm: DataManager, logger):
    """Demonstrate analytics and performance reporting"""
    logger.info("\n=== Analytics and Reporting Demo ===")
    
    # Add some performance metrics for demonstration
    logger.info("Adding sample performance data...")
    
    # Simulate adding sensor readings for analytics
    for i in range(50):
        timestamp = datetime.now() - timedelta(minutes=i)
        
        # Battery performance data
        battery_reading = SensorReading(
            sensor_id="battery_main",
            sensor_type="battery",
            timestamp=timestamp,
            value={
                "voltage": 12.6 - (i * 0.01),  # Gradual voltage drop
                "current": -3.2 - (i * 0.05),  # Increasing current draw
                "temperature": 28.5 + (i * 0.1),  # Temperature rise
                "cycle_count": 1250 + (i // 10)
            },
            quality=0.98 - (i * 0.001)  # Slight quality degradation
        )
        await dm.store_sensor_reading(battery_reading)
        
        # Navigation performance data
        nav_reading = SensorReading(
            sensor_id="gps_primary",
            sensor_type="navigation",
            timestamp=timestamp,
            value={
                "coverage_map": {
                    "total_area": 1000,
                    "covered_area": min(1000, i * 20),
                    "overlap": i * 2
                }
            },
            quality=0.95
        )
        await dm.store_sensor_reading(nav_reading)
    
    # Generate comprehensive performance report
    logger.info("Generating performance report...")
    start_time = asyncio.get_event_loop().time()
    
    report = await dm.get_performance_report()
    
    report_time = (asyncio.get_event_loop().time() - start_time) * 1000
    logger.info(f"Generated report in {report_time:.2f}ms")
    
    # Display key metrics
    logger.info(f"Overall Health Score: {report['overall_health_score']:.1f}/100")
    
    if 'performance_metrics' in report:
        metrics = report['performance_metrics']
        if 'coverage_efficiency' in metrics:
            coverage = metrics['coverage_efficiency']
            logger.info(f"Coverage Efficiency: {coverage['value']:.1f}% (confidence: {coverage['confidence']:.2f})")
        
        if 'battery_performance' in metrics:
            battery = metrics['battery_performance']
            logger.info(f"Battery Performance: {battery['value']:.1f}/100 (confidence: {battery['confidence']:.2f})")
    
    # Display maintenance predictions
    if 'maintenance_predictions' in report:
        predictions = report['maintenance_predictions']
        logger.info(f"Maintenance Predictions: {len(predictions)} items")
        for pred in predictions[:3]:  # Show first 3
            logger.info(f"  - {pred['component']}: {pred['maintenance_type']} ({pred['urgency']} priority)")
    
    # Display recommendations
    if 'recommendations' in report:
        logger.info("System Recommendations:")
        for rec in report['recommendations'][:3]:  # Show first 3
            logger.info(f"  • {rec}")
    
    # Calculate coverage efficiency specifically
    coverage_efficiency = await dm.calculate_coverage_efficiency()
    logger.info(f"Current Coverage Efficiency: {coverage_efficiency:.1f}%")


async def demonstrate_system_health_monitoring(dm: DataManager, logger):
    """Demonstrate system health monitoring"""
    logger.info("\n=== System Health Monitoring Demo ===")
    
    # Get comprehensive system health
    health_status = await dm.get_system_health()
    
    logger.info(f"System Status: {health_status['status'].upper()}")
    logger.info(f"Overall Health Score: {health_status['overall_health_score']:.1f}/100")
    
    # Display component health
    if 'components' in health_status:
        components = health_status['components']
        
        if 'cache' in components:
            cache_info = components['cache']
            logger.info(f"Cache: {'Connected' if cache_info.get('connected') else 'Disconnected'}")
            logger.info(f"  Hit Rate: {cache_info.get('hit_rate', 0):.1f}%")
        
        if 'database' in components:
            db_info = components['database']
            if 'sensor_readings_count' in db_info:
                logger.info(f"Database: {db_info['sensor_readings_count']} sensor readings stored")
        
        if 'performance' in components:
            perf_info = components['performance']
            logger.info(f"Performance: {perf_info['total_operations']} total operations")
            logger.info(f"  Average Response Time: {perf_info['avg_response_time']:.2f}ms")
            if perf_info['errors'] > 0:
                logger.warning(f"  Errors: {perf_info['errors']}")


async def demonstrate_data_export_backup(dm: DataManager, logger):
    """Demonstrate data export and backup functionality"""
    logger.info("\n=== Data Export and Backup Demo ===")
    
    # Export recent data
    logger.info("Exporting system data...")
    try:
        export_path = await dm.export_data(
            data_types=["sensor_readings", "configurations"],
            start_time=datetime.now() - timedelta(hours=1),
            format="json"
        )
        logger.info(f"✓ Data exported to: {export_path}")
        
        # Check export file size
        export_file = Path(export_path)
        if export_file.exists():
            size_kb = export_file.stat().st_size / 1024
            logger.info(f"  Export file size: {size_kb:.1f} KB")
    
    except Exception as e:
        logger.error(f"✗ Export failed: {e}")
    
    # Create system backup
    logger.info("Creating system backup...")
    try:
        backup_path = await dm.backup_system_data()
        logger.info(f"✓ System backup created: {backup_path}")
        
        # Check backup file size
        backup_file = Path(backup_path)
        if backup_file.exists():
            size_kb = backup_file.stat().st_size / 1024
            logger.info(f"  Backup file size: {size_kb:.1f} KB")
    
    except Exception as e:
        logger.error(f"✗ Backup failed: {e}")


async def demonstrate_emergency_scenarios(dm: DataManager, logger):
    """Demonstrate emergency stop and recovery scenarios"""
    logger.info("\n=== Emergency Scenarios Demo ===")
    
    # Set normal operating state
    await dm.update_system_state(
        new_state=SystemState.MOWING.value,
        mode=OperationMode.AUTOMATIC.value,
        battery_level=80.0,
        current_task="mowing_side_yard",
        progress=0.6
    )
    logger.info("Set normal mowing operation")
    
    # Trigger emergency stop
    logger.info("Triggering emergency stop...")
    await dm.emergency_stop("Obstacle detected - person in mowing area")
    
    # Verify emergency state
    emergency_state = await dm.get_current_state()
    logger.info(f"Emergency state: {emergency_state.state}")
    logger.info(f"Emergency reason: {emergency_state.metadata.get('emergency_reason', 'N/A')}")
    
    # Demonstrate recovery check
    can_resume = await dm.state.can_resume_operation()
    logger.info(f"Can resume operation: {can_resume}")
    
    # Simulate recovery
    if not can_resume:
        logger.info("Clearing emergency condition...")
        await dm.update_system_state(
            new_state=SystemState.IDLE.value,
            mode=OperationMode.AUTOMATIC.value,
            current_task=None,
            metadata={"emergency_cleared": True}
        )
        
        can_resume = await dm.state.can_resume_operation()
        logger.info(f"Can resume after clearing: {can_resume}")


async def main():
    """Main demo function"""
    logger = await setup_logging()
    logger.info("Starting Data Management System Demo")
    
    # Load configuration
    config = await load_demo_config()
    logger.info(f"Loaded configuration for database: {config.get('database_path', 'default')}")
    
    # Initialize data manager
    dm = DataManager(config)
    
    try:
        # Initialize system
        logger.info("Initializing data management system...")
        success = await dm.initialize()
        
        if not success:
            logger.error("Failed to initialize data management system")
            return
        
        logger.info("✓ Data management system initialized successfully")
        
        # Run demonstrations
        await demonstrate_sensor_data_operations(dm, logger)
        await demonstrate_state_management(dm, logger)
        await demonstrate_configuration_management(dm, logger)
        await demonstrate_analytics_and_reporting(dm, logger)
        await demonstrate_system_health_monitoring(dm, logger)
        await demonstrate_data_export_backup(dm, logger)
        await demonstrate_emergency_scenarios(dm, logger)
        
        logger.info("\n=== Demo Completed Successfully ===")
        logger.info("Data management system demonstrated:")
        logger.info("✓ High-performance sensor data storage and retrieval")
        logger.info("✓ Persistent state management with recovery")
        logger.info("✓ Configuration management with caching")
        logger.info("✓ Advanced analytics and performance reporting")
        logger.info("✓ System health monitoring")
        logger.info("✓ Data export and backup functionality")
        logger.info("✓ Emergency handling and recovery")
        
    except Exception as e:
        logger.error(f"Demo failed: {e}")
        raise
    
    finally:
        # Cleanup
        logger.info("Shutting down data management system...")
        await dm.shutdown()
        logger.info("Demo cleanup completed")


if __name__ == "__main__":
    asyncio.run(main())
