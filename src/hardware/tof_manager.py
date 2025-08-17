#!/usr/bin/env python3
from __future__ import annotations
"""
VL53L0X Time-of-Flight Sensor Manager for LawnBerry Pi
Based on Adafruit CircuitPython VL53L0X example for multiple sensors
Handles proper address assignment for dual ToF sensors
"""

import time
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

try:
    import board  # type: ignore
    import busio  # type: ignore
    from digitalio import DigitalInOut  # type: ignore
    from adafruit_vl53l0x import VL53L0X  # type: ignore
    HAS_HARDWARE = True
except Exception as e:  # pragma: no cover - running without hardware or lgpio failure
    HAS_HARDWARE = False
    logging.warning(
        f"VL53L0X hardware libs not available (Blinka/lgpio issue) - simulation mode: {e}"
    )
    board = None  # type: ignore
    busio = None  # type: ignore
    DigitalInOut = object  # type: ignore
    VL53L0X = object  # type: ignore

# Import hardware error for proper error handling
try:
    from .exceptions import HardwareError
except ImportError:  # pragma: no cover - fallback if exceptions module missing
    class HardwareError(Exception):
        pass

from .gpio_wrapper import GPIO


class _FakeToFSensor:
    """Lightweight fake ToF sensor used as a fallback when real sensors fail to initialize."""
    def __init__(self, name: str, address: int):
        self._name = name
        self._address = address
        self._distance = 200  # mm default

    @property
    def range(self):
        # Return a stable-ish simulated distance; could be randomized later
        return self._distance

    def start_continuous(self):
        return None

    def stop_continuous(self):
        return None

    def set_address(self, addr: int):
        self._address = addr
        return None



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
    
    def __init__(self, gpio_manager=None):
        self.logger = logging.getLogger(__name__)
        self.i2c = None
        self.sensors: Dict[str, VL53L0X] = {}
        self.shutdown_pins: Dict[str, DigitalInOut] = {}
        self.sensor_configs: List[ToFSensorConfig] = []
        # Track which GPIO pins this manager configured to avoid conflicts
        self._configured_pins = set()
        self._initialized = False
        self._lock = asyncio.Lock()
        # Hold a reference to the shared GPIOManager if provided
        self.gpio_manager = gpio_manager

        # Default sensor configuration based on hardware setup
        # Both sensors are physically connected and tested
        self.default_configs = [
            ToFSensorConfig(
                name="tof_left",
                shutdown_pin=22,  # GPIO 22
                interrupt_pin=6,  # GPIO 6
                target_address=0x30  # Left sensor gets changed to 0x30
            ),
            ToFSensorConfig(
                name="tof_right",
                shutdown_pin=23,  # GPIO 23
                interrupt_pin=12, # GPIO 12
                target_address=0x29  # Right sensor keeps default 0x29
            )
        ]
    
    async def initialize(self, sensor_configs: Optional[List[ToFSensorConfig]] = None) -> bool:
        """Initialize all ToF sensors with proper address assignment"""
        async with self._lock:
            if self._initialized:
                return True
            
            if not HAS_HARDWARE:
                # Allow an override to require hardware and fail fast in CI/dev if needed
                require_hw = False
                try:
                    import os

                    require_hw = os.getenv("LAWNBERY_REQUIRE_HARDWARE", "0") in ("1", "true", "True")
                except Exception:
                    require_hw = False

                if require_hw:
                    self.logger.error("Hardware required but VL53L0X libs not available")
                    return False

                self.logger.warning("Running in simulation mode - ToF sensors not available; creating simulated sensors")
                # Create simulated sensors so callers receive readings in simulation
                self.sensor_configs = sensor_configs or self.default_configs
                for cfg in self.sensor_configs:
                    fake = _FakeToFSensor(cfg.name, cfg.target_address)
                    self.sensors[cfg.name] = fake
                self._initialized = True
                self.logger.info(f"Initialized {len(self.sensors)} simulated ToF sensors")
                return True
            
            try:
                # Use provided configs or defaults
                self.sensor_configs = sensor_configs or self.default_configs
                
                # Initialize I2C bus
                self.i2c = busio.I2C(board.SCL, board.SDA)
                self.logger.info("I2C bus initialized for ToF sensors")
                
                # Initialize shutdown pins - ALL sensors OFF initially
                # Prefer using GPIOManager if available to centralize claims
                await self._setup_shutdown_pins()
                
                # Initialize sensors one by one with proper address assignment
                await self._initialize_sensors_sequence()

                # If no physical sensors were initialized, create simulated fallback sensors
                if not self.sensors:
                    self.logger.warning("No ToF sensors initialized physically; creating simulated fallback sensors")
                    for cfg in self.sensor_configs:
                        fake = _FakeToFSensor(cfg.name, cfg.target_address)
                        self.sensors[cfg.name] = fake

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
        if GPIO:
            try:
                # Set mode once for all ToF GPIO operations
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
            except Exception as e:
                self.logger.debug(f"GPIO setmode/setwarnings failed: {e}")

        for config in self.sensor_configs:
            try:
                # Prefer centralized GPIO management to avoid duplicate claims
                if self.gpio_manager is not None:
                    if config.shutdown_pin not in self._configured_pins:
                        # Ask GPIOManager to setup the pin (it will claim internally)
                        try:
                            await self.gpio_manager.setup_pin(config.shutdown_pin, 'output', initial=0)
                            self._configured_pins.add(config.shutdown_pin)
                            self.logger.debug(f"GPIO {config.shutdown_pin} configured for {config.name} (OFF) via GPIOManager")
                        except Exception as e:
                            claimant = getattr(GPIO, 'get_claimant', lambda p: None)(config.shutdown_pin) if hasattr(GPIO, 'get_claimant') else None
                            if claimant:
                                self.logger.warning(f"Failed to setup shutdown pin for {config.name} (pin {config.shutdown_pin}): {e} - currently claimed by {claimant}")
                            else:
                                self.logger.warning(f"Failed to setup shutdown pin for {config.name} (pin {config.shutdown_pin}): {e}")
                            # Mark as configured to avoid repeated attempts
                            self._configured_pins.add(config.shutdown_pin)
                    else:
                        self.logger.debug(f"GPIO {config.shutdown_pin} already configured; skipping setup for {config.name}")

                else:
                    # Fallback to raw GPIO wrapper behavior
                    if GPIO:
                        if config.shutdown_pin not in self._configured_pins:
                            claimant = getattr(GPIO, 'get_claimant', lambda p: None)(config.shutdown_pin) if hasattr(GPIO, 'get_claimant') else None
                            if claimant:
                                self.logger.debug(f"GPIO shutdown pin {config.shutdown_pin} currently claimed by {claimant} before setup for {config.name}")
                            GPIO.setup(config.shutdown_pin, GPIO.OUT, initial=GPIO.LOW)
                            self._configured_pins.add(config.shutdown_pin)
                            self.logger.debug(f"GPIO {config.shutdown_pin} configured for {config.name} (OFF)")
                        else:
                            self.logger.debug(f"GPIO {config.shutdown_pin} already configured; skipping setup for {config.name}")
                    else:  # pragma: no cover - simulation mode
                        self.logger.debug(f"Simulation mode: skipping GPIO setup for {config.name}")
            except Exception as e:  # pragma: no cover - hardware failure
                # Log and continue; another manager may have claimed the pin already
                claimant = getattr(GPIO, 'get_claimant', lambda p: None)(config.shutdown_pin) if hasattr(GPIO, 'get_claimant') else None
                if claimant:
                    self.logger.warning(f"Failed to setup shutdown pin for {config.name} (pin {config.shutdown_pin}): {e} - currently claimed by {claimant}")
                else:
                    self.logger.warning(f"Failed to setup shutdown pin for {config.name} (pin {config.shutdown_pin}): {e}")
                # Mark as configured to avoid repeated attempts
                self._configured_pins.add(config.shutdown_pin)
        
        # Small delay to ensure all sensors are off
        await asyncio.sleep(0.1)
        self.logger.info("All ToF sensors powered down")
    
    async def _initialize_sensors_sequence(self):
        """Initialize sensors one by one with proper timeout protection"""
        self.logger.info("Starting ToF sensor initialization sequence...")

        for i, config in enumerate(self.sensor_configs):
            try:
                self.logger.info(f"Initializing sensor {i+1}/{len(self.sensor_configs)}: {config.name}")

                # Use timeout for each sensor initialization
                await asyncio.wait_for(
                    self._initialize_single_sensor_with_timeout(i, config),
                    timeout=30.0  # 30 second timeout per sensor
                )
                self.logger.info(f"✅ {config.name} initialized successfully")
                
            except asyncio.TimeoutError:
                self.logger.error(f"❌ {config.name} initialization timed out after 30 seconds")
                continue  # Continue with next sensor
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize {config.name}: {e}")
                continue  # Continue with next sensor
        
        if not self.sensors:
            self.logger.warning("No physical ToF sensors were initialized in sequence")

        self.logger.info(f"🎉 ToF sensor initialization complete! Initialized {len(self.sensors)} sensors")
        
        # Verify all sensors are accessible
        if self.sensors:
            await self._verify_sensors()

    async def _initialize_single_sensor_with_timeout(self, i: int, config: ToFSensorConfig):
        """Initialize a single ToF sensor with proper error handling"""
        # Step 1: Turn ON this sensor
        # Power on the sensor via GPIOManager or raw GPIO
        if self.gpio_manager is not None:
            try:
                await self.gpio_manager.write_pin(config.shutdown_pin, 1)
            except Exception as e:
                claimant = getattr(GPIO, 'get_claimant', lambda p: None)(config.shutdown_pin) if hasattr(GPIO, 'get_claimant') else None
                self.logger.warning(f"Failed to set GPIO {config.shutdown_pin} HIGH for {config.name} via GPIOManager: {e} (claimant={claimant})")
        else:
            if GPIO:
                try:
                    claimant = getattr(GPIO, 'get_claimant', lambda p: None)(config.shutdown_pin) if hasattr(GPIO, 'get_claimant') else None
                    if claimant:
                        self.logger.debug(f"Writing HIGH to pin {config.shutdown_pin} for {config.name} (claimed by {claimant})")
                    GPIO.output(config.shutdown_pin, GPIO.HIGH)
                except Exception as e:
                    self.logger.warning(f"Failed to set GPIO {config.shutdown_pin} HIGH for {config.name}: {e}")
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
        if hasattr(sensor, 'measurement_timing_budget'):
            def set_timing():
                sensor.measurement_timing_budget = config.measurement_timing_budget
                
            await asyncio.get_event_loop().run_in_executor(None, set_timing)
            self.logger.debug(f"Set timing budget to {config.measurement_timing_budget}us for {config.name}")
        
        # Step 5: Change address if NOT the last sensor
        if i < len(self.sensor_configs) - 1:
            await self._change_sensor_address_with_timeout(sensor, config)
        
        # Step 6: Store sensor reference
        self.sensors[config.name] = sensor

    async def _change_sensor_address_with_timeout(self, sensor, config: ToFSensorConfig):
        """Change sensor address with proper timeout and verification"""
        old_address = 0x29
        new_address = config.target_address
        self.logger.info(f"Changing {config.name} address from 0x{old_address:02x} to 0x{new_address:02x}")
        
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
            self.logger.info(f"✅ Address change successful - {config.name} now at 0x{new_address:02x}")
        else:
            self.logger.error(f"❌ Address change failed - {config.name} not found at 0x{new_address:02x}")
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
                address=target_address
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
                if hasattr(sensor, 'stop_continuous'):
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

            # Turn off all sensors using GPIO with timeout protection
            for config in self.sensor_configs:
                try:
                    if self.gpio_manager is not None and config.shutdown_pin in self._configured_pins:
                        try:
                            await self.gpio_manager.write_pin(config.shutdown_pin, 0)
                            self.logger.debug(f"GPIO {config.shutdown_pin} set LOW for {config.name} via GPIOManager")
                        except Exception as e:
                            self.logger.warning(f"Failed to set GPIO {config.shutdown_pin} LOW for {config.name} via GPIOManager: {e}")
                    elif GPIO and config.shutdown_pin in self._configured_pins:
                        try:
                            GPIO.output(config.shutdown_pin, GPIO.LOW)
                            self.logger.debug(f"GPIO {config.shutdown_pin} set LOW for {config.name}")
                        except Exception as e:
                            self.logger.warning(f"Failed to set GPIO {config.shutdown_pin} LOW for {config.name}: {e}")
                    else:
                        self.logger.debug(f"Skipping GPIO LOW for {config.name} (pin not configured or in simulation)")
                except Exception as e:
                    self.logger.warning(f"Unexpected error while turning off pin {config.shutdown_pin}: {e}")

            # Small delay to ensure sensors are off
            await asyncio.sleep(0.1)

            # Clean up GPIO
            if GPIO:
                try:
                    # Only cleanup if we configured any pins
                    if self._configured_pins:
                        GPIO.cleanup()
                        self.logger.info("GPIO cleanup completed")
                    else:
                        self.logger.debug("No GPIO pins configured by ToF manager; skipping global cleanup")
                except Exception as e:
                    self.logger.warning(f"GPIO cleanup warning: {e}")
            
            # Clear data structures
            self.sensors.clear()
            self.shutdown_pins.clear()
            self.sensor_configs.clear()
            # Release claimed pins (use GPIOManager if available)
            try:
                if self.gpio_manager is not None and hasattr(self.gpio_manager, 'write_pin'):
                    # Also call release helpers on wrapper if present
                    for p in list(self._configured_pins):
                        try:
                            if hasattr(GPIO, 'release_pin'):
                                GPIO.release_pin(p)
                        except Exception:
                            pass
                else:
                    if GPIO and hasattr(GPIO, 'release_pin'):
                        for p in list(self._configured_pins):
                            try:
                                GPIO.release_pin(p)
                            except Exception:
                                pass
            except Exception:
                pass
            
            # Close I2C bus if it exists
            if hasattr(self, 'i2c') and self.i2c:
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
            # Force GPIO cleanup as last resort
            if GPIO:
                try:
                    GPIO.cleanup()
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
            try:
                if GPIO and GPIO.input(config.shutdown_pin):
                    pin_state = "HIGH (ON)"
                elif GPIO:
                    pin_state = "LOW (OFF)"
                else:
                    pin_state = "unavailable"
            except Exception:
                pin_state = "error"
            
            status[config.name] = {
                "initialized": sensor_active,
                "shutdown_pin": config.shutdown_pin,
                "target_address": f"0x{config.target_address:02x}",
                "measurement_timing_budget": config.measurement_timing_budget,
                "pin_state": pin_state
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
