"""Demo script showing hardware interface layer usage"""

import asyncio
import logging
from datetime import datetime

from src.hardware import HardwareInterface, create_hardware_interface


async def main():
    """Demonstrate hardware interface functionality"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Create hardware interface
    hw = create_hardware_interface("config/hardware.yaml")
    
    try:
        # Initialize hardware
        logger.info("Initializing hardware interface...")
        success = await hw.initialize()
        if not success:
            logger.error("Failed to initialize hardware")
            return
        
        logger.info("Hardware interface initialized successfully")
        
        # Scan for I2C devices
        logger.info("Scanning I2C bus...")
        devices = await hw.scan_i2c_devices()
        logger.info(f"Found I2C devices at addresses: {[hex(addr) for addr in devices]}")
        
        # List available sensors
        sensors = hw.list_available_sensors()
        logger.info(f"Available sensors: {sensors}")
        
        # Test RoboHAT commands
        logger.info("Testing RoboHAT commands...")
        await hw.send_robohat_command('rc_disable')
        await asyncio.sleep(0.5)
        
        await hw.send_robohat_command('pwm', 1500, 1500)  # Neutral position
        await asyncio.sleep(0.5)
        
        await hw.send_robohat_command('enc_zero')
        await asyncio.sleep(0.5)
        
        # Read sensor data
        logger.info("Reading sensor data...")
        for i in range(5):
            sensor_data = await hw.get_all_sensor_data()
            
            for sensor_name, reading in sensor_data.items():
                logger.info(f"{sensor_name}: {reading.value} {reading.unit} "
                           f"(quality: {reading.quality:.2f})")
            
            # Get system health
            health = await hw.get_system_health()
            logger.info(f"System healthy: {health['overall_healthy']}")
            
            await asyncio.sleep(2)
        
        # Test GPIO control
        logger.info("Testing GPIO control...")
        await hw.control_gpio_pin('blade_enable', 0)  # Disable blade
        blade_status = await hw.read_gpio_pin('blade_enable')
        logger.info(f"Blade enable status: {blade_status}")
        
        # Get camera frame
        logger.info("Testing camera...")
        frame = await hw.get_camera_frame()
        if frame:
            logger.info(f"Camera frame: {frame.width}x{frame.height}, "
                       f"size: {len(frame.data)} bytes")
        
        # Test dynamic sensor addition
        logger.info("Testing dynamic sensor management...")
        success = await hw.add_sensor("test_sensor", "tof_sensor", {
            "i2c_address": 0x31,
            "shutdown_pin": 26
        })
        
        if success:
            logger.info("Test sensor added successfully")
            
            # Read from new sensor
            test_reading = await hw.get_sensor_data("test_sensor")
            if test_reading:
                logger.info(f"Test sensor reading: {test_reading.value}")
            
            # Remove test sensor
            await hw.remove_sensor("test_sensor")
            logger.info("Test sensor removed")
        
        # Demonstrate error handling
        logger.info("Testing error handling...")
        try:
            await hw.get_sensor_data("nonexistent_sensor")
        except Exception as e:
            logger.info(f"Expected error caught: {e}")
        
        # Monitor system for a while
        logger.info("Monitoring system for 10 seconds...")
        start_time = datetime.now()
        
        while (datetime.now() - start_time).seconds < 10:
            health = await hw.get_system_health()
            cached_data = await hw.get_cached_sensor_data()
            
            logger.info(f"Health: {health['overall_healthy']}, "
                       f"Cached readings: {len(cached_data)}")
            
            await asyncio.sleep(2)
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}")
    finally:
        # Shutdown
        logger.info("Shutting down hardware interface...")
        await hw.shutdown()
        logger.info("Demo complete")


if __name__ == "__main__":
    asyncio.run(main())
