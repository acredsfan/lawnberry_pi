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
import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import subprocess
import sys

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
from .board_utils import default_tof_right_interrupt_pin


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

        # Number of consecutive valid (non-zero, in-range) reads required
        # before a sensor is considered healthy. Allow override from env.
        try:
            self._required_good_reads = int(os.getenv('LAWNBERY_TOF_REQUIRED_GOOD_READS', '3'))
        except Exception:
            self._required_good_reads = 3

        # Maximum age for a 'good' read in seconds
        try:
            self._good_read_age_s = float(os.getenv('LAWNBERY_TOF_GOOD_READ_AGE_S', '10'))
        except Exception:
            self._good_read_age_s = 10.0

        # Control GPIO usage for ToF init. Modes:
        # - 'never': require GPIO sequencing (default if not set and GPIO available)
        # - 'auto': use GPIO; if GPIO fails and both 0x29 and 0x30 are present, fall back to no-GPIO
        # - 'always': skip GPIO and require both 0x29 and 0x30 present (pre-assigned)
        try:
            self._no_gpio_mode = os.getenv('LAWNBERY_TOF_NO_GPIO', 'auto').lower()
            if self._no_gpio_mode not in ('never', 'auto', 'always'):
                self._no_gpio_mode = 'auto'
        except Exception:
            self._no_gpio_mode = 'auto'

        # Per-sensor initialization timeout (seconds). Keep this modest so overall
        # service startup doesn't block for too long if a sensor is slow or absent.
        try:
            self._per_sensor_timeout_s = float(os.getenv('LAWNBERY_TOF_PER_SENSOR_TIMEOUT_S', '12.0'))
        except Exception:
            self._per_sensor_timeout_s = 12.0

        # Path to persisted state enabling no-GPIO after addresses are confirmed once
        try:
            # Repo root is three parents up from this file: src/hardware/tof_manager.py
            self._repo_root = Path(__file__).resolve().parents[2]
        except Exception:
            self._repo_root = Path('.')
        self._state_file = self._repo_root / 'data' / 'tof_no_gpio.json'
        self._persist_no_gpio = False
        try:
            if self._state_file.exists():
                data = json.loads(self._state_file.read_text())
                self._persist_no_gpio = bool(data.get('no_gpio_always', False))
        except Exception:
            self._persist_no_gpio = False

        # Track auto-assign attempt (prevent repeated GPIO toggling attempts in one process)
        self._auto_assign_attempted = False

        # Auto-assign feature flags (env-driven)
        try:
            self._auto_assign_enabled = os.getenv('LAWNBERY_TOF_AUTO_ASSIGN_ON_MISSING', '0') in ('1','true','True')
        except Exception:
            self._auto_assign_enabled = False
        try:
            self._auto_assign_timeout_s = float(os.getenv('LAWNBERY_TOF_AUTO_ASSIGN_TIMEOUT_S', '60'))
        except Exception:
            self._auto_assign_timeout_s = 60.0

        # Default sensor configuration based on hardware setup
        # Both sensors are physically connected and tested
        self.default_configs = [
            ToFSensorConfig(
                name="tof_left",
                shutdown_pin=22,  # GPIO 22
                interrupt_pin=6,  # GPIO 6
                target_address=0x29  # Left sensor stays at default 0x29
            ),
            ToFSensorConfig(
                name="tof_right",
                shutdown_pin=23,  # GPIO 23
                # Board-aware default: Pi 5 => BCM8 to avoid UART4 on 12/13
                interrupt_pin=default_tof_right_interrupt_pin(),
                target_address=0x30  # Right sensor is changed to 0x30
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
            
            # Optional pre-scan helper
            def _scan_bus() -> List[int]:
                addrs: List[int] = []
                try:
                    i2c = board.I2C()
                    if i2c.try_lock():
                        try:
                            addrs = i2c.scan()
                        finally:
                            i2c.unlock()
                except Exception:
                    pass
                return addrs

            # Determine effective no-GPIO mode: env override 'never' wins, otherwise
            # if a persisted flag exists (addresses confirmed previously), prefer 'always'
            effective_no_gpio = self._no_gpio_mode
            if effective_no_gpio != 'never' and self._persist_no_gpio:
                effective_no_gpio = 'always'

            # If in 'always' no-GPIO mode, DO NOT use GPIO under any circumstance.
            # Attempt to initialize without GPIO; this will safely initialize any sensors
            # already present on distinct addresses (partial init allowed). If that fails,
            # bail out without touching GPIO so we don't power cycle or re-sequence sensors.
            if effective_no_gpio == 'always':
                ok = await self._initialize_without_gpio_if_possible(sensor_configs)
                if ok:
                    self._initialized = True
                    return True
                # Optional: attempt one-time auto assignment if explicitly enabled
                if self._auto_assign_enabled and not self._auto_assign_attempted:
                    self.logger.warning("No-GPIO mode 'always' and addresses missing - attempting one-time auto assignment via script")
                    tried = await self._attempt_auto_assign_addresses()
                    if tried:
                        # Retry no-GPIO init after assignment
                        ok2 = await self._initialize_without_gpio_if_possible(sensor_configs)
                        if ok2:
                            self._initialized = True
                            return True
                self.logger.error(
                    "ToF no-GPIO mode is 'always' but required I2C addresses were not accessible. "
                    "Skipping GPIO sequencing by design. Ensure sensors are assigned to 0x29 and 0x30 "
                    "(use scripts/assign_vl53l0x_adafruit.py), then retry."
                )
                return False

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

                # If no physical sensors were initialized, attempt no-GPIO fallback in 'auto' mode
                if not self.sensors and effective_no_gpio in ("auto",):
                    try:
                        ok = await self._initialize_without_gpio_if_possible(sensor_configs)
                        if not ok:
                            self.logger.debug("No-GPIO fallback did not succeed; will use simulated sensors")
                    except Exception as fe:
                        self.logger.debug(f"No-GPIO fallback error: {fe}")

                # If sensors initialized (either via GPIO or no-GPIO), and both addresses are present,
                # persist the no-GPIO flag so future runs can skip GPIO sequencing.
                try:
                    addrs_after = await asyncio.get_event_loop().run_in_executor(None, _scan_bus)
                    if 0x29 in addrs_after and 0x30 in addrs_after:
                        self._persist_no_gpio_flag()
                except Exception:
                    pass

                # If still no sensors, create simulated fallback sensors
                if not self.sensors:
                    self.logger.warning("No ToF sensors initialized physically; creating simulated fallback sensors")
                    for cfg in self.sensor_configs:
                        fake = _FakeToFSensor(cfg.name, cfg.target_address)
                        self.sensors[cfg.name] = fake

                self._initialized = True
                self.logger.info(f"Successfully initialized {len(self.sensors)} ToF sensors")
                return True
                
            except Exception as e:
                self.logger.warning(f"GPIO-based ToF initialization failed: {e}")
                # In 'auto' mode, attempt no-GPIO fallback if both addresses present already
                if self._no_gpio_mode == 'auto':
                    try:
                        addrs = await asyncio.get_event_loop().run_in_executor(None, _scan_bus)
                        if 0x29 in addrs and 0x30 in addrs:
                            ok = await self._initialize_without_gpio_if_possible(sensor_configs)
                            if ok:
                                self._initialized = True
                                return True
                    except Exception as fe:
                        self.logger.debug(f"No-GPIO fallback attempt failed: {fe}")
                # Cleanup on failure
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
                    timeout=self._per_sensor_timeout_s  # configurable per-sensor timeout
                )
                self.logger.info(f"✅ {config.name} initialized successfully")
                
            except asyncio.TimeoutError:
                self.logger.error(f"❌ {config.name} initialization timed out after {self._per_sensor_timeout_s:.0f} seconds")
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
        
        # Step 5: Change address if target_address differs from default 0x29
        try:
            desired = int(getattr(config, 'target_address', 0x29))
        except Exception:
            desired = 0x29
        if desired != 0x29:
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

    async def _initialize_without_gpio_if_possible(self, sensor_configs: Optional[List[ToFSensorConfig]] = None) -> bool:
        """Initialize ToF sensors without using GPIO sequencing.

        Only safe if the bus already has distinct addresses (0x29 and 0x30) present.
        Returns True on success, False otherwise.
        """
        try:
            # Scan I2C bus to validate addresses
            addrs: List[int] = []
            try:
                tmp_i2c = board.I2C()
                if tmp_i2c.try_lock():
                    try:
                        addrs = tmp_i2c.scan()
                    finally:
                        tmp_i2c.unlock()
            except Exception:
                pass

            # Filter to only known ToF addresses present
            present_tof_addrs = [a for a in addrs if a in (0x29, 0x30)]
            if not present_tof_addrs:
                self.logger.warning("No-GPIO init skipped: no ToF addresses (0x29/0x30) detected on the bus")
                return False

            # Create dedicated I2C bus
            self.i2c = busio.I2C(board.SCL, board.SDA)

            cfgs = sensor_configs or self.default_configs
            # Build an available address pool from bus
            address_pool: List[int] = list(present_tof_addrs)
            for cfg in cfgs:
                target = int(getattr(cfg, 'target_address', 0x29))
                # Choose target if available, otherwise use the other one if present
                addr = target if target in address_pool else (0x30 if 0x30 in address_pool else 0x29 if 0x29 in address_pool else None)
                if addr is None:
                    # Allow partial initialization without failing the whole process
                    self.logger.warning(f"No available ToF address for {cfg.name} during no-GPIO init; skipping this sensor")
                    continue
                try:
                    sensor = VL53L0X(self.i2c, address=addr)
                    # Start continuous mode in executor
                    await asyncio.get_event_loop().run_in_executor(None, sensor.start_continuous)
                    self.sensors[cfg.name] = sensor
                    # Consume address so next sensor uses the remaining one
                    try:
                        address_pool.remove(addr)
                    except Exception:
                        pass
                except Exception as e:
                    self.logger.error(f"Failed to initialize VL53L0X at {hex(addr)} for {cfg.name} without GPIO: {e}")
                    # Continue attempting other sensors if possible
                    continue

            # If none could be initialized, indicate failure
            if not self.sensors:
                self.logger.warning("No-GPIO ToF init found no accessible sensors at 0x29/0x30")
                return False

            # Verify access by reading once
            await self._verify_sensors()
            self.logger.info("ToF sensors initialized without GPIO sequencing")

            # If both addresses are now present, persist flag for future runs
            try:
                if 0x29 in addrs and 0x30 in addrs:
                    self._persist_no_gpio_flag()
            except Exception:
                pass
            return True
        except Exception as e:
            self.logger.error(f"No-GPIO ToF initialization encountered an error: {e}")
            return False

    async def _attempt_auto_assign_addresses(self) -> bool:
        """Attempt one-time auto assignment by invoking the Adafruit-style script.

        Returns True if the script was invoked (regardless of success). The caller
        will rescan and verify addresses.
        """
        self._auto_assign_attempted = True
        try:
            script_path = self._repo_root / 'scripts' / 'assign_vl53l0x_adafruit.py'
            if not script_path.exists():
                self.logger.error(f"Auto-assign script not found: {script_path}")
                return False
            # Use the current interpreter (assumed to be the correct venv) and timeout
            cmd = [sys.executable, str(script_path)]
            self.logger.info(f"Running auto-assign script with timeout {self._auto_assign_timeout_s:.0f}s: {cmd}")
            try:
                subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=self._auto_assign_timeout_s)
            except subprocess.TimeoutExpired:
                self.logger.error("Auto-assign script timed out")
                return True
            except Exception as e:
                self.logger.error(f"Auto-assign script error: {e}")
                return True
            return True
        except Exception as e:
            self.logger.error(f"Auto-assign attempt failed unexpectedly: {e}")
            return True

    async def recover_if_missing(self) -> bool:
        """Attempt a soft, no-GPIO recovery if sensors appear missing or unhealthy.

        Strategy:
        - Quickly scan the bus for 0x29/0x30.
        - If both present and manager already has sensors, and recent good reads exist, do nothing.
        - Otherwise, stop continuous mode on any existing sensors and re-run the no-GPIO init path.

        Returns True if a recovery attempt was made and resulted in sensors being (re)initialized; False if no action was needed or recovery failed.
        """
        if not HAS_HARDWARE:
            return False

        # Helper to scan bus safely
        def _scan_bus_now() -> List[int]:
            addrs: List[int] = []
            try:
                i2c = board.I2C()
                if i2c.try_lock():
                    try:
                        addrs = i2c.scan()
                    finally:
                        i2c.unlock()
            except Exception:
                pass
            return addrs

        addrs = await asyncio.get_event_loop().run_in_executor(None, _scan_bus_now)
        present = [a for a in addrs if a in (0x29, 0x30)]

        # Quick health assessment from cached status
        status = {}
        try:
            status = self.get_sensor_status()
        except Exception:
            status = {}

        # Determine if we need recovery: either addresses missing or lifecycle not ok
        need_recover = False
        if not (0x29 in present and 0x30 in present):
            need_recover = True
        else:
            # If both addresses present but manager not in 'ok' state, attempt recovery
            try:
                # Consider recovery when any sensor not 'ok'
                for name, info in status.items():
                    if info.get('status') != 'ok':
                        need_recover = True
                        break
            except Exception:
                need_recover = True

        if not need_recover:
            return False

        self.logger.warning("ToF health check triggered soft recovery (no-GPIO)")
        try:
            # Stop current continuous modes quickly (best-effort)
            try:
                await asyncio.wait_for(self.stop_continuous_mode(), timeout=3.0)
            except Exception:
                pass

            # Attempt re-initialization without GPIO with timeout
            try:
                ok = await asyncio.wait_for(self._initialize_without_gpio_if_possible(self.sensor_configs or self.default_configs), timeout=8.0)
            except asyncio.TimeoutError:
                self.logger.error("No-GPIO recovery timed out")
                return False
            except Exception as e:
                self.logger.error(f"No-GPIO recovery error: {e}")
                return False

            if ok:
                self.logger.info("ToF soft recovery completed successfully")
                return True
            else:
                self.logger.error("ToF soft recovery path did not reinitialize sensors")
                return False
        except Exception as e:
            self.logger.error(f"Unexpected error during ToF recovery: {e}")
            return False

    def _persist_no_gpio_flag(self) -> None:
        """Persist a flag indicating we can safely run in no-GPIO mode on future runs.

        This only writes when both 0x29 and 0x30 have been confirmed on the bus.
        Honors env override LAWNBERY_TOF_NO_GPIO=never by not forcing future behavior.
        """
        try:
            # Do not persist if user explicitly set 'never'
            if self._no_gpio_mode == 'never':
                return
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'no_gpio_always': True,
                'confirmed_at': datetime.now().isoformat(),
                'note': 'ToF addresses 0x29 and 0x30 confirmed; safe to skip GPIO sequencing on future runs.'
            }
            self._state_file.write_text(json.dumps(payload, indent=2))
            self._persist_no_gpio = True
            self.logger.info(f"Persisted ToF no-GPIO flag at {self._state_file}")
        except Exception as e:
            self.logger.debug(f"Failed to persist no-GPIO flag: {e}")
    
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
            # Cache last read on the sensor object for status reporting
            try:
                setattr(sensor, '_last_distance', distance_mm)
                setattr(sensor, '_last_read_ts', datetime.now().isoformat())
                # Update consecutive good-read streak tracking on the sensor.
                # Consider a 'good' read one that is >0 and within expected max
                # (use measurement_timing_budget or a sensible default).
                try:
                    prev_streak = int(getattr(sensor, '_good_read_streak', 0))
                except Exception:
                    prev_streak = 0

                try:
                    val = float(distance_mm)
                except Exception:
                    val = 0.0

                # Define in-range as >0 and less than 2000mm (2m) as a sensible
                # heuristic; sensor reports large sentinel values for out-of-range.
                if val > 0 and val < 2000:
                    setattr(sensor, '_good_read_streak', prev_streak + 1)
                    setattr(sensor, '_last_good_ts', datetime.now().isoformat())
                else:
                    setattr(sensor, '_good_read_streak', 0)
            except Exception:
                pass
            
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

            # Clean up GPIO (per-pin) to avoid closing the global chip handle
            if GPIO:
                try:
                    if self._configured_pins and hasattr(GPIO, 'cleanup_pins'):
                        GPIO.cleanup_pins(list(self._configured_pins))  # type: ignore
                        self.logger.info("GPIO per-pin cleanup completed")
                    elif self._configured_pins and hasattr(GPIO, 'free_pin'):
                        for p in list(self._configured_pins):
                            try:
                                GPIO.free_pin(p)  # type: ignore
                            except Exception as e:
                                self.logger.warning(f"GPIO free_pin warning for {p}: {e}")
                        self.logger.info("GPIO free_pin cleanup completed")
                    else:
                        self.logger.debug("No GPIO pins configured by ToF manager; skipping cleanup")
                except Exception as e:
                    self.logger.warning(f"GPIO per-pin cleanup warning: {e}")
            
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
            # Do not globally close the GPIO chip; per-pin cleanup already done above
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
            
            # Attempt to surface last-read information if available on the sensor
            last_read = None
            last_read_ts = None
            try:
                sensor = self.sensors.get(config.name)
                if sensor is not None and hasattr(sensor, 'range'):
                    # We don't call sensor.range here to avoid triggering hardware reads,
                    # but if the manager stored a cached last_read we can expose it. If not
                    # present, keep None.
                    last_read = getattr(sensor, '_last_distance', None)
                    last_read_ts = getattr(sensor, '_last_read_ts', None)
            except Exception:
                last_read = None
                last_read_ts = None

            # Determine a richer sensor lifecycle status:
            # - 'not_initialized' : manager hasn't finished initialization
            # - 'initializing'    : manager initialized but no valid non-zero read yet
            # - 'ok'              : manager initialized and recent non-zero read available
            lifecycle_status = "not_initialized"
            last_read_age = None
            try:
                if last_read_ts:
                    # last_read_ts stored as ISO string
                    last_dt = datetime.fromisoformat(last_read_ts)
                    last_read_age = (datetime.now() - last_dt).total_seconds()
            except Exception:
                last_read_age = None

            if not self._initialized:
                lifecycle_status = "not_initialized"
            else:
                # Manager initialized. Require a stable run of consecutive good
                # reads before considering a sensor 'ok'. This filters transient
                # zeros and out-of-range artifacts during warm-up.
                good_streak = int(getattr(sensor, '_good_read_streak', 0)) if sensor is not None else 0
                last_good_ts = getattr(sensor, '_last_good_ts', None) if sensor is not None else None
                last_good_age = None
                try:
                    if last_good_ts:
                        last_good_age = (datetime.now() - datetime.fromisoformat(last_good_ts)).total_seconds()
                except Exception:
                    last_good_age = None

                # Determine if the last good read is recent enough
                recent_good = (last_good_age is None) or (last_good_age <= self._good_read_age_s)

                if good_streak >= self._required_good_reads and recent_good:
                    lifecycle_status = "ok"
                else:
                    lifecycle_status = "initializing"

            status[config.name] = {
                "initialized": sensor_active,
                "shutdown_pin": config.shutdown_pin,
                "target_address": f"0x{config.target_address:02x}",
                "measurement_timing_budget": config.measurement_timing_budget,
                "pin_state": pin_state,
                # richer lifecycle status
                "status": lifecycle_status,
                "last_read_mm": last_read,
                "last_read_ts": last_read_ts,
                "last_read_age_s": last_read_age,
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
