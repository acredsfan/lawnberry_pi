#!/usr/bin/env python3
"""
VL53L0X Time-of-Flight Sensor Manager for LawnBerry Pi
Based on Adafruit CircuitPython VL53L0X example for multiple sensors
Handles proper address assignment for dual ToF sensors
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

try:
    import board
    import busio
    import lgpio
    from adafruit_vl53l0x import VL53L0X
    from digitalio import DigitalInOut

    HAS_HARDWARE = True
except ImportError:  # pragma: no cover - hardware specific
    HAS_HARDWARE = False
    lgpio = None
    logging.warning("VL53L0X hardware libraries not available - running in simulation mode")

# Import hardware error for proper error handling
try:
    from .exceptions import HardwareError
except ImportError:
    # Fallback if exceptions module doesn't exist
    class HardwareError(Exception):
        pass


@dataclass
class ToFSensorConfig:
    """Configuration for a single ToF sensor"""

    name: str
    shutdown_pin: int
    interrupt_pin: Optional[int] = None
    target_address: int = 0x29
    measurement_timing_budget: int = 200000  # microseconds (200ms)


@dataclass
class ToFReading:
    """ToF sensor reading data"""

    timestamp: datetime
    sensor_name: str
    distance_mm: int
    range_status: str
    address: int


class ToFSensorManager:
    """Manager for multiple VL53L0X Time-of-Flight sensors"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.i2c = None
        self.sensors: Dict[str, VL53L0X] = {}
        self.shutdown_pins: Dict[str, DigitalInOut] = {}
        self.sensor_configs: List[ToFSensorConfig] = []
        self._initialized = False
        self._lock = asyncio.Lock()
        self._chip: Optional[int] = None

        # Default sensor configuration based on hardware setup
        # Both sensors are physically connected and tested
        self.default_configs = [
            ToFSensorConfig(
                name="tof_left",
                shutdown_pin=22,  # GPIO 22
                interrupt_pin=6,  # GPIO 6
                target_address=0x30,  # Left sensor gets changed to 0x30
            ),
            ToFSensorConfig(
                name="tof_right",
                shutdown_pin=23,  # GPIO 23
                interrupt_pin=12,  # GPIO 12
                target_address=0x29,  # Right sensor keeps default 0x29
            ),
        ]

    async def initialize(self, sensor_configs: Optional[List[ToFSensorConfig]] = None) -> bool:
        """Initialize all ToF sensors with proper address assignment"""
        async with self._lock:
            if self._initialized:
                return True

            if not HAS_HARDWARE:
                self.logger.warning("Running in simulation mode - ToF sensors not available")
                self._initialized = True
                return True

            try:
                # Use provided configs or defaults
                self.sensor_configs = sensor_configs or self.default_configs

                # Initialize I2C bus
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.logger.info("I2C bus initialized for ToF sensors")

                # Initialize shutdown pins - ALL sensors OFF initially
                await self._setup_shutdown_pins()

                # Initialize sensors one by one with proper address assignment
                await self._initialize_sensors_sequence()

                self._initialized = True
                self.logger.info(f"Successfully initialized {len(self.sensors)} ToF sensors")
                return True

            except Exception as e:
                self.logger.error(f"Failed to initialize ToF sensors: {e}")
                await self._cleanup()
                return False

    async def _setup_shutdown_pins(self):
        """Setup all shutdown pins and turn OFF all sensors"""
        self.logger.info("Setting up ToF sensor shutdown pins...")
        if lgpio:
            try:
                self._chip = lgpio.gpiochip_open(0)
            except Exception as e:  # pragma: no cover - hardware specific
                self.logger.error(f"Failed to open lgpio chip: {e}")
                raise

            for config in self.sensor_configs:
                try:
                    lgpio.gpio_claim_output(self._chip, config.shutdown_pin, lgpio.LOW)
                    self.logger.debug(
                        f"GPIO {config.shutdown_pin} configured for {config.name} (OFF)"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to setup shutdown pin for {config.name}: {e}")
                    raise

            await asyncio.sleep(0.1)  # Ensure all sensors are off
            self.logger.info("All ToF sensors powered down")
        else:
            self.logger.warning("lgpio not available - skipping shutdown pin setup")

    async def _initialize_sensors_sequence(self):
        """Initialize sensors one by one with proper timeout protection"""
        self.logger.info("Starting ToF sensor initialization sequence...")

        for i, config in enumerate(self.sensor_configs):
            try:
                self.logger.info(
                    f"Initializing sensor {i+1}/{len(self.sensor_configs)}: {config.name}"
                )

                # Use timeout for each sensor initialization
                await asyncio.wait_for(
                    self._initialize_single_sensor_with_timeout(i, config),
                    timeout=30.0,  # 30 second timeout per sensor
                )
                self.logger.info(f"✅ {config.name} initialized successfully")

            except asyncio.TimeoutError:
                self.logger.error(f"❌ {config.name} initialization timed out after 30 seconds")
                continue  # Continue with next sensor
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {config.name}: {e}")
                continue  # Continue with next sensor

        if not self.sensors:
            raise HardwareError("Failed to initialize any ToF sensors")

        self.logger.info(
            f"🎉 ToF sensor initialization complete! Initialized {len(self.sensors)} sensors"
        )

        # Verify all sensors are accessible
        if self.sensors:
            await self._verify_sensors()

    async def _initialize_single_sensor_with_timeout(self, i: int, config: ToFSensorConfig):
        """Initialize a single ToF sensor with proper error handling"""
        # Step 1: Turn ON this sensor
        if lgpio and self._chip is not None:
            lgpio.gpio_write(self._chip, config.shutdown_pin, lgpio.HIGH)
        else:
            raise HardwareError("lgpio not available for ToF sensor initialization")
        await asyncio.sleep(0.1)  # Allow sensor to boot
        self.logger.debug(f"Powered on {config.name} via GPIO {config.shutdown_pin}")

        # Step 2: Create VL53L0X instance with executor to prevent blocking
        def create_sensor():
            return VL53L0X(self.i2c)

        sensor = await asyncio.get_event_loop().run_in_executor(None, create_sensor)
        self.logger.debug(f"Created VL53L0X instance for {config.name}")

        # Step 3: Start continuous mode with executor to prevent blocking
        def start_continuous():
            sensor.start_continuous()

        await asyncio.get_event_loop().run_in_executor(None, start_continuous)
        self.logger.debug(f"Started continuous mode for {config.name}")

        # Step 4: Set measurement timing budget if specified
        if hasattr(sensor, "measurement_timing_budget"):

            def set_timing():
                sensor.measurement_timing_budget = config.measurement_timing_budget

            await asyncio.get_event_loop().run_in_executor(None, set_timing)
            self.logger.debug(
                f"Set timing budget to {config.measurement_timing_budget}us for {config.name}"
            )

        # Step 5: Change address if NOT the last sensor
        if i < len(self.sensor_configs) - 1:
            await self._change_sensor_address_with_timeout(sensor, config)

        # Step 6: Store sensor reference
        self.sensors[config.name] = sensor

    async def _change_sensor_address_with_timeout(self, sensor, config: ToFSensorConfig):
        """Change sensor address with proper timeout and verification"""
        old_address = 0x29
        new_address = config.target_address
        self.logger.info(
            f"Changing {config.name} address from 0x{old_address:02x} to 0x{new_address:02x}"
        )

        # Set new address with executor to prevent blocking
        def set_address():
            sensor.set_address(new_address)

        await asyncio.get_event_loop().run_in_executor(None, set_address)
        await asyncio.sleep(0.1)  # Allow address change to settle

        # Verify address change worked by scanning I2C bus
        def scan_bus():
            if self.i2c.try_lock():
                try:
                    return self.i2c.scan()
                finally:
                    self.i2c.unlock()
            return []

        devices = await asyncio.get_event_loop().run_in_executor(None, scan_bus)

        if new_address in devices:
            self.logger.info(
                f"✅ Address change successful - {config.name} now at 0x{new_address:02x}"
            )
        else:
            self.logger.error(
                f"❌ Address change failed - {config.name} not found at 0x{new_address:02x}"
            )
            self.logger.debug(f"Available I2C devices: {[hex(d) for d in devices]}")
            raise HardwareError(f"Failed to change {config.name} address to 0x{new_address:02x}")

        # Verify all sensors are accessible
        await self._verify_sensors()

    async def _verify_sensors(self):
        """Verify all sensors are accessible at their assigned addresses"""
        self.logger.info("Verifying ToF sensor accessibility...")

        for config in self.sensor_configs:
            if config.name in self.sensors:
                try:
                    sensor = self.sensors[config.name]
                    # Try to read a distance to verify sensor is working
                    distance = sensor.range
                    self.logger.info(f"✅ {config.name} verified - distance: {distance}mm")
                except Exception as e:
                    self.logger.warning(f"⚠️ {config.name} verification failed: {e}")

    async def read_sensor(self, sensor_name: str) -> Optional[ToFReading]:
        """Read distance from a specific sensor"""
        if not self._initialized:
            self.logger.error("ToF manager not initialized")
            return None

        if sensor_name not in self.sensors:
            self.logger.error(f"Sensor {sensor_name} not found")
            return None

        try:
            sensor = self.sensors[sensor_name]
            distance_mm = sensor.range

            # Find the target address for this sensor
            target_address = 0x29  # default
            for config in self.sensor_configs:
                if config.name == sensor_name:
                    target_address = config.target_address
                    break

            return ToFReading(
                timestamp=datetime.now(),
                sensor_name=sensor_name,
                distance_mm=distance_mm,
                range_status="valid" if distance_mm < 2000 else "out_of_range",
                address=target_address,
            )

        except Exception as e:
            self.logger.error(f"Failed to read {sensor_name}: {e}")
            return None

    async def read_all_sensors(self) -> Dict[str, ToFReading]:
        """Read distances from all sensors"""
        readings = {}

        for sensor_name in self.sensors.keys():
            reading = await self.read_sensor(sensor_name)
            if reading:
                readings[sensor_name] = reading

        return readings

    async def stop_continuous_mode(self):
        """Stop continuous mode on all sensors"""
        self.logger.info("Stopping continuous mode on all ToF sensors...")

        for sensor_name, sensor in self.sensors.items():
            try:
                if hasattr(sensor, "stop_continuous"):
                    sensor.stop_continuous()
                    self.logger.debug(f"Stopped continuous mode on {sensor_name}")
            except Exception as e:
                self.logger.warning(f"Failed to stop continuous mode on {sensor_name}: {e}")

    async def _cleanup(self):
        """Clean up resources with timeout protection"""
        self.logger.info("Starting ToF sensor cleanup...")

        try:
            # Stop continuous mode with timeout
            await asyncio.wait_for(self.stop_continuous_mode(), timeout=5.0)

            if lgpio and self._chip is not None:
                for config in self.sensor_configs:
                    try:
                        lgpio.gpio_write(self._chip, config.shutdown_pin, lgpio.LOW)
                        self.logger.debug(f"GPIO {config.shutdown_pin} set LOW for {config.name}")
                    except Exception as e:
                        self.logger.warning(f"Failed to set GPIO {config.shutdown_pin} LOW: {e}")

                await asyncio.sleep(0.1)  # Ensure sensors are off

            # Clean up GPIO
            try:
                GPIO.cleanup()
                self.logger.info("GPIO cleanup completed")
            except Exception as e:
                self.logger.warning(f"GPIO cleanup warning: {e}")

            # Clear data structures
            self.sensors.clear()
            self.shutdown_pins.clear()
            self.sensor_configs.clear()

            # Close I2C bus if it exists
            if hasattr(self, "i2c") and self.i2c:
                try:
                    self.i2c.deinit()
                    self.logger.debug("I2C bus deinitialized")
                except Exception as e:
                    self.logger.debug(f"I2C deinit warning: {e}")

            self.logger.info("ToF sensor cleanup completed successfully")

        except asyncio.TimeoutError:
            self.logger.error("ToF sensor cleanup timed out")
        except Exception as e:
            self.logger.error(f"Error during ToF cleanup: {e}")
        finally:
            # Force lgpio cleanup as last resort
            if lgpio and self._chip is not None:
                try:
                    lgpio.gpiochip_close(self._chip)
                except Exception:
                    pass

    async def shutdown(self):
        """Shutdown ToF sensor manager"""
        self.logger.info("Shutting down ToF sensor manager...")

        async with self._lock:
            if self._initialized:
                await self._cleanup()
                self._initialized = False

        self.logger.info("ToF sensor manager shutdown complete")

    def get_sensor_status(self) -> Dict[str, Dict]:
        """Get status information for all sensors"""
        status = {}

        for config in self.sensor_configs:
            sensor_active = config.name in self.sensors

            # Get GPIO pin state
            pin_state = "unknown"
            if lgpio and self._chip is not None:
                try:
                    if lgpio.gpio_read(self._chip, config.shutdown_pin):
                        pin_state = "HIGH (ON)"
                    else:
                        pin_state = "LOW (OFF)"
                except Exception:
                    pin_state = "error"

            status[config.name] = {
                "initialized": sensor_active,
                "shutdown_pin": config.shutdown_pin,
                "target_address": f"0x{config.target_address:02x}",
                "measurement_timing_budget": config.measurement_timing_budget,
                "pin_state": pin_state,
            }

        return status


# Test function for debugging
async def test_tof_manager():
    """Test the ToF sensor manager"""
    manager = ToFSensorManager()

    print("Testing ToF Sensor Manager...")

    # Initialize
    success = await manager.initialize()
    print(f"Initialization: {'✅ Success' if success else '❌ Failed'}")

    if success:
        # Get status
        status = manager.get_sensor_status()
        print("\nSensor Status:")
        for name, info in status.items():
            print(f"  {name}: {info}")

        # Read sensors
        print("\nReading sensors...")
        for i in range(5):
            readings = await manager.read_all_sensors()
            if readings:
                print(f"Reading {i+1}:")
                for name, reading in readings.items():
                    print(f"  {name}: {reading.distance_mm}mm (0x{reading.address:02x})")
            await asyncio.sleep(1)

        # Shutdown
        await manager.shutdown()

    print("Test complete!")


if __name__ == "__main__":
    # Run test if executed directly
    asyncio.run(test_tof_manager())
