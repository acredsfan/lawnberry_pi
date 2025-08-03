#!/usr/bin/env python3
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
    import board
    import busio
    from digitalio import DigitalInOut
    from adafruit_vl53l0x import VL53L0X
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False
    logging.warning("VL53L0X hardware libraries not available - running in simulation mode")


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
        
        # Default sensor configuration based on hardware.yaml
        self.default_configs = [
            ToFSensorConfig(
                name="tof_left",
                shutdown_pin=22,  # GPIO 22
                interrupt_pin=6,  # GPIO 6
                target_address=0x29  # Keep left sensor at default address
            ),
            ToFSensorConfig(
                name="tof_right", 
                shutdown_pin=23,  # GPIO 23
                interrupt_pin=12, # GPIO 12
                target_address=0x30  # Change right sensor to 0x30
            )
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
        
        for config in self.sensor_configs:
            try:
                # For Raspberry Pi GPIO with CircuitPython, we need to use a different approach
                # Since board.D22/D23 may not be available, we'll use RPi.GPIO instead
                import RPi.GPIO as GPIO
                
                # Setup GPIO if not already done
                GPIO.setmode(GPIO.BCM)
                GPIO.setwarnings(False)
                
                # Setup the pin as output and turn OFF sensor
                GPIO.setup(config.shutdown_pin, GPIO.OUT, initial=GPIO.LOW)
                
                self.logger.debug(f"GPIO {config.shutdown_pin} configured for {config.name} (OFF)")
                
            except Exception as e:
                self.logger.error(f"Failed to setup shutdown pin for {config.name}: {e}")
                raise
        
        # Small delay to ensure all sensors are off
        await asyncio.sleep(0.1)
        self.logger.info("All ToF sensors powered down")
    
    async def _initialize_sensors_sequence(self):
        """Initialize sensors one by one following Adafruit example pattern"""
        self.logger.info("Starting ToF sensor initialization sequence...")
        
        import RPi.GPIO as GPIO
        
        for i, config in enumerate(self.sensor_configs):
            try:
                self.logger.info(f"Initializing sensor {i+1}/{len(self.sensor_configs)}: {config.name}")
                
                # Step 1: Turn ON this sensor
                GPIO.output(config.shutdown_pin, GPIO.HIGH)
                await asyncio.sleep(0.1)  # Allow sensor to boot
                
                # Step 2: Create VL53L0X instance (at default address 0x29)
                sensor = VL53L0X(self.i2c)
                
                # Step 3: Start continuous mode for better performance
                sensor.start_continuous()
                
                # Step 4: Set measurement timing budget if specified
                if hasattr(sensor, 'measurement_timing_budget'):
                    sensor.measurement_timing_budget = config.measurement_timing_budget
                
                # Step 5: Change address if NOT the last sensor and NOT default address
                if i < len(self.sensor_configs) - 1 and config.target_address != 0x29:
                    self.logger.info(f"Changing {config.name} address from 0x29 to 0x{config.target_address:02x}")
                    sensor.set_address(config.target_address)
                    await asyncio.sleep(0.1)  # Allow address change to settle
                
                # Step 6: Store sensor reference
                self.sensors[config.name] = sensor
                
                self.logger.info(f"✅ {config.name} initialized at address 0x{config.target_address:02x}")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize {config.name}: {e}")
                raise
        
        self.logger.info("🎉 All ToF sensors initialization complete!")
        
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
        """Clean up resources"""
        try:
            await self.stop_continuous_mode()
            
            # Turn off all sensors using RPi.GPIO
            import RPi.GPIO as GPIO
            for config in self.sensor_configs:
                try:
                    GPIO.output(config.shutdown_pin, GPIO.LOW)
                except:
                    pass
                    
            GPIO.cleanup()
            
            self.sensors.clear()
            self.shutdown_pins.clear()
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
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
                import RPi.GPIO as GPIO
                if GPIO.input(config.shutdown_pin):
                    pin_state = "HIGH (ON)"
                else:
                    pin_state = "LOW (OFF)"
            except:
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
