#!/usr/bin/env python3
"""
Fix ToF Sensor Address Configuration
Strict one-at-a-time power-up for dual VL53L0X sensors to split addresses (0x29, 0x30)
"""

import time
import logging
import sys
import os

# Add src to path for imports (not strictly needed here)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus
    except ImportError:
        smbus = None

try:
    from gpiozero import DigitalOutputDevice
except ImportError:
    DigitalOutputDevice = None


def setup_logging() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    return logging.getLogger(__name__)


class ToFSensorManager:
    def __init__(self) -> None:
        self.logger = setup_logging()
        # Pins per hardware.yaml
        self.left_shutdown_pin = 22
        self.right_shutdown_pin = 23

        # I2C addresses
        self.default_address = 0x29
        self.left_target_address = 0x29
        self.right_target_address = 0x30

        # I2C
        self.bus_number = 1
        self.bus = None

        # GPIO
        self.left_shutdown: DigitalOutputDevice | None = None
        self.right_shutdown: DigitalOutputDevice | None = None

        # Leave sensors on after setup
        self.keep_powered = True

    def initialize_hardware(self) -> bool:
        try:
            if not smbus:
                raise RuntimeError("SMBus not available. Install python3-smbus or smbus2")
            if DigitalOutputDevice is None:
                raise RuntimeError("gpiozero not available. Install python3-gpiozero")

            self.bus = smbus.SMBus(self.bus_number)
            self.left_shutdown = DigitalOutputDevice(self.left_shutdown_pin, initial_value=False)
            self.right_shutdown = DigitalOutputDevice(self.right_shutdown_pin, initial_value=False)
            self.logger.info("I2C bus initialized; both sensors in shutdown (XSHUT low)")
            return True
        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            return False

    def scan_i2c_bus(self) -> list[int]:
        devices: list[int] = []
        try:
            for address in range(0x03, 0x78):
                try:
                    self.bus.read_byte(address)
                    devices.append(address)
                except OSError:
                    pass
        except Exception as e:
            self.logger.error(f"I2C scan failed: {e}")
        return devices

    def power_both_off(self) -> None:
        assert self.left_shutdown and self.right_shutdown
        self.left_shutdown.off()
        self.right_shutdown.off()
        time.sleep(0.2)

    def power_right_only(self) -> None:
        assert self.left_shutdown and self.right_shutdown
        self.left_shutdown.off()
        self.right_shutdown.on()
        time.sleep(0.4)

    def power_left_only(self) -> None:
        assert self.left_shutdown and self.right_shutdown
        self.right_shutdown.off()
        self.left_shutdown.on()
        time.sleep(0.4)

    def power_both_on(self) -> None:
        assert self.left_shutdown and self.right_shutdown
        self.left_shutdown.on()
        self.right_shutdown.on()
        time.sleep(0.4)

    def change_sensor_address(self, old_address: int, new_address: int) -> bool:
        try:
            self.bus.write_byte_data(old_address, 0x8A, new_address & 0x7F)
            time.sleep(0.1)
            # Verify by pinging new address
            try:
                self.bus.read_byte(new_address)
                return True
            except Exception:
                return False
        except Exception as e:
            self.logger.error(f"Address change failed 0x{old_address:02x} -> 0x{new_address:02x}: {e}")
            return False

    def setup_dual_sensors(self) -> bool:
        self.logger.info("Starting strict one-at-a-time ToF address setup...")
        try:
            # 1) Both OFF
            self.power_both_off()

            # 2) RIGHT only ON -> must see 0x29
            self.power_right_only()
            dev = self.scan_i2c_bus()
            self.logger.info(f"Scan (right only): {[hex(a) for a in dev]}")
            if self.default_address not in dev:
                raise RuntimeError("Right sensor not detected at 0x29 with left OFF")

            # 3) Change RIGHT to 0x30 (retries)
            for attempt in range(3):
                if self.change_sensor_address(self.default_address, self.right_target_address):
                    time.sleep(0.2)
                    dev = self.scan_i2c_bus()
                    self.logger.info(f"Post-change scan: {[hex(a) for a in dev]}")
                    if self.right_target_address in dev and self.default_address not in dev:
                        break
                time.sleep(0.2)
            else:
                raise RuntimeError("Failed to set right sensor to 0x30 after retries")

            # 4) Turn LEFT ON while keeping RIGHT ON
            self.left_shutdown.on()
            time.sleep(0.5)
            dev = self.scan_i2c_bus()
            self.logger.info(f"Scan (both on): {[hex(a) for a in dev]}")
            if not (self.left_target_address in dev and self.right_target_address in dev):
                raise RuntimeError("Expected both 0x29 and 0x30 present after enabling left")

            self.logger.info("SUCCESS: LEFT=0x29, RIGHT=0x30")
            if self.keep_powered:
                self.power_both_on()
            return True
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            if self.keep_powered:
                # Best effort: leave both on for debugging
                try:
                    self.power_both_on()
                except Exception:
                    pass
            return False

    def cleanup(self) -> None:
        try:
            if self.bus:
                self.bus.close()
        except Exception:
            pass


def main() -> bool:
    log = setup_logging()
    log.info("=== ToF Sensor Address Configuration Tool ===")
    mgr = ToFSensorManager()
    if not mgr.initialize_hardware():
        return False
    try:
        ok = mgr.setup_dual_sensors()
        return ok
    finally:
        mgr.cleanup()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
