#!/usr/bin/env python3
"""
Fix ToF Sensor Address Configuration
This script properly initializes dual VL53L0X ToF sensors to use different I2C addresses
"""

import time
import logging
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus
    except ImportError:
        smbus = None

try:
    import gpiozero
    from gpiozero import DigitalOutputDevice
except ImportError:
    gpiozero = None

def setup_logging():
    """Setup logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

class ToFSensorManager:
    """Manages dual VL53L0X ToF sensors with address configuration"""
    
    def __init__(self):
        self.logger = setup_logging()
        
        # GPIO pins from hardware.yaml
        self.left_shutdown_pin = 22
        self.right_shutdown_pin = 23
        
        # I2C addresses
        self.default_address = 0x29
        self.left_target_address = 0x29   # Left sensor stays at default
        self.right_target_address = 0x30  # Right sensor moves to 0x30
        
        # I2C bus
        self.bus_number = 1
        self.bus = None
        
        # GPIO objects
        self.left_shutdown = None
        self.right_shutdown = None
    
    def initialize_hardware(self):
        """Initialize I2C bus and GPIO pins"""
        try:
            # Initialize I2C bus
            if not smbus:
                raise RuntimeError("SMBus not available. Install python3-smbus")
            
            self.bus = smbus.SMBus(self.bus_number)
            self.logger.info(f"I2C bus {self.bus_number} initialized")
            
            # Initialize GPIO pins
            if not gpiozero:
                raise RuntimeError("GPIOZero not available. Install python3-gpiozero")
            
            self.left_shutdown = DigitalOutputDevice(self.left_shutdown_pin, initial_value=False)
            self.right_shutdown = DigitalOutputDevice(self.right_shutdown_pin, initial_value=False)
            self.logger.info("GPIO pins initialized (both sensors in shutdown)")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            return False
    
    def scan_i2c_bus(self):
        """Scan I2C bus for devices"""
        self.logger.info("Scanning I2C bus...")
        devices = []
        
        try:
            for address in range(0x03, 0x78):
                try:
                    self.bus.read_byte(address)
                    devices.append(address)
                    self.logger.info(f"Found device at 0x{address:02x}")
                except OSError:
                    pass
            
            return devices
            
        except Exception as e:
            self.logger.error(f"I2C scan failed: {e}")
            return []
    
    def read_sensor_id(self, address):
        """Read VL53L0X sensor identification"""
        try:
            # VL53L0X identification register
            id_reg = 0xC0
            sensor_id = self.bus.read_byte_data(address, id_reg)
            return sensor_id
            
        except Exception as e:
            self.logger.warning(f"Failed to read sensor ID at 0x{address:02x}: {e}")
            return None
    
    def change_sensor_address(self, old_address, new_address):
        """Change VL53L0X I2C address"""
        try:
            # VL53L0X address change register
            addr_reg = 0x8A
            
            # Write new address (shifted left by 1 for 7-bit addressing)
            new_addr_value = new_address << 1
            self.bus.write_byte_data(old_address, addr_reg, new_addr_value)
            
            time.sleep(0.1)  # Give sensor time to update
            
            # Verify the change
            sensor_id = self.read_sensor_id(new_address)
            if sensor_id == 0xEE:  # VL53L0X expected ID
                self.logger.info(f"Successfully changed address from 0x{old_address:02x} to 0x{new_address:02x}")
                return True
            else:
                sensor_id_str = f"0x{sensor_id:02x}" if sensor_id is not None else "None"
                self.logger.error(f"Address change verification failed - sensor ID: {sensor_id_str}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to change address from 0x{old_address:02x} to 0x{new_address:02x}: {e}")
            return False
    
    def initialize_sensor(self, address):
        """Basic VL53L0X initialization"""
        try:
            # Check sensor ID first
            sensor_id = self.read_sensor_id(address)
            if sensor_id != 0xEE:
                self.logger.error(f"Invalid sensor ID at 0x{address:02x}: 0x{sensor_id:02x if sensor_id else 'None'}")
                return False
            
            # Basic initialization sequence (simplified)
            # In a full implementation, this would include the complete VL53L0X init sequence
            
            # Power up the sensor
            self.bus.write_byte_data(address, 0x00, 0x01)
            time.sleep(0.01)
            
            # Set default configuration (simplified)
            self.bus.write_byte_data(address, 0x01, 0xFF)  # Enable all GPIO
            self.bus.write_byte_data(address, 0x02, 0x00)  # Set GPIO config
            
            self.logger.info(f"Sensor at 0x{address:02x} initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize sensor at 0x{address:02x}: {e}")
            return False
    
    def setup_dual_sensors(self):
        """Setup dual ToF sensors with proper addressing"""
        self.logger.info("Starting dual ToF sensor setup...")
        
        try:
            # Step 1: Ensure both sensors are in shutdown
            self.left_shutdown.off()   # Shutdown left sensor
            self.right_shutdown.off()  # Shutdown right sensor
            time.sleep(0.1)
            self.logger.info("Both sensors in shutdown mode")
            
            # Step 2: Scan bus (should be empty of ToF sensors)
            initial_devices = self.scan_i2c_bus()
            tof_devices = [addr for addr in initial_devices if addr in [0x29, 0x30]]
            if tof_devices:
                self.logger.warning(f"ToF sensors still detected during shutdown: {[hex(addr) for addr in tof_devices]}")
            
            # Step 3: Bring up right sensor first and change its address
            self.logger.info("Bringing up right sensor to change its address...")
            self.right_shutdown.on()  # Enable right sensor
            time.sleep(0.1)  # Allow sensor to boot
            
            # Check if sensor appears at default address
            sensor_id = self.read_sensor_id(self.default_address)
            if sensor_id != 0xEE:
                self.logger.error(f"Right sensor not detected at default address 0x{self.default_address:02x} (sensor_id: 0x{sensor_id:02x if sensor_id else 'None'})")
                # Try to scan and see what's there
                devices = self.scan_i2c_bus()
                self.logger.info(f"Devices found during right sensor startup: {[hex(addr) for addr in devices]}")
                raise RuntimeError(f"Right sensor not detected at default address 0x{self.default_address:02x}")
            
            self.logger.info(f"Right sensor detected at default address 0x{self.default_address:02x}")
            
            # Change right sensor address from 0x29 to 0x30
            if not self.change_sensor_address(self.default_address, self.right_target_address):
                raise RuntimeError("Failed to change right sensor address")
            
            # Initialize right sensor at new address
            if not self.initialize_sensor(self.right_target_address):
                raise RuntimeError("Failed to initialize right sensor")
            
            # Step 4: Bring up left sensor (it will use default address 0x29)
            self.logger.info("Bringing up left sensor at default address...")
            self.left_shutdown.on()  # Enable left sensor
            time.sleep(0.1)  # Allow sensor to boot
            
            # Initialize left sensor at default address
            if not self.initialize_sensor(self.left_target_address):
                raise RuntimeError("Failed to initialize left sensor")
            
            # Step 5: Final verification
            self.logger.info("Verifying both sensors are working...")
            final_devices = self.scan_i2c_bus()
            
            left_present = self.left_target_address in final_devices
            right_present = self.right_target_address in final_devices
            
            if left_present and right_present:
                self.logger.info("SUCCESS: Both ToF sensors are now properly configured!")
                self.logger.info(f"  Left sensor:  0x{self.left_target_address:02x}")
                self.logger.info(f"  Right sensor: 0x{self.right_target_address:02x}")
                return True
            else:
                self.logger.error(f"FAILED: Left present: {left_present}, Right present: {right_present}")
                return False
                
        except Exception as e:
            self.logger.error(f"Dual sensor setup failed: {e}")
            return False
    
    def test_sensor_readings(self):
        """Test basic distance readings from both sensors"""
        self.logger.info("Testing sensor readings...")
        
        try:
            for name, address in [("Left", self.left_target_address), ("Right", self.right_target_address)]:
                try:
                    # Start measurement (simplified)
                    self.bus.write_byte_data(address, 0x00, 0x01)
                    time.sleep(0.05)  # Wait for measurement
                    
                    # Read result (this is a simplified read - real VL53L0X has complex protocol)
                    # Just verify we can communicate
                    status = self.bus.read_byte_data(address, 0x13)  # Range status
                    self.logger.info(f"{name} sensor (0x{address:02x}) communication test: OK (status: 0x{status:02x})")
                    
                except Exception as e:
                    self.logger.error(f"{name} sensor (0x{address:02x}) communication test: FAILED - {e}")
                    
        except Exception as e:
            self.logger.error(f"Sensor testing failed: {e}")
    
    def cleanup(self):
        """Clean up resources"""
        try:
            if self.left_shutdown:
                self.left_shutdown.close()
            if self.right_shutdown:
                self.right_shutdown.close()
            if self.bus:
                self.bus.close()
            self.logger.info("Resources cleaned up")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

def main():
    """Main function"""
    logger = setup_logging()
    logger.info("=== ToF Sensor Address Configuration Tool ===")
    
    manager = ToFSensorManager()
    
    try:
        # Initialize hardware
        if not manager.initialize_hardware():
            logger.error("Hardware initialization failed")
            return False
        
        # Show initial state
        logger.info("Initial I2C bus state:")
        initial_devices = manager.scan_i2c_bus()
        
        # Setup dual sensors
        success = manager.setup_dual_sensors()
        
        if success:
            # Test communication
            manager.test_sensor_readings()
            
            logger.info("\n=== CONFIGURATION COMPLETE ===")
            logger.info("ToF sensors are now properly configured:")
            logger.info("  Left sensor (tof_left):   0x29")
            logger.info("  Right sensor (tof_right): 0x30")
            logger.info("\nYou can now run the hardware detection again to verify both sensors are detected.")
        else:
            logger.error("\n=== CONFIGURATION FAILED ===")
            logger.error("Please check hardware connections and try again.")
        
        return success
        
    except KeyboardInterrupt:
        logger.info("Configuration interrupted by user")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False
        
    finally:
        manager.cleanup()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
