"""Hardware managers for different interface types"""

import asyncio
import json
import logging
import os
import random
import subprocess
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import serial
except Exception:
    serial = None
try:
    import cv2
except Exception:
    cv2 = None

# Picamera2 (preferred on Raspberry Pi OS Bookworm)
try:
    from picamera2 import Picamera2

    _PICAMERA2_AVAILABLE = True
except Exception:
    Picamera2 = None  # type: ignore
    _PICAMERA2_AVAILABLE = False

try:
    import numpy as np
except Exception:
    np = None

from .board_utils import default_tof_right_interrupt_pin

# Raspberry Pi 4B/5 compatibility is provided via gpio_wrapper
from .gpio_wrapper import GPIO

try:  # Hardware I2C library may be unavailable during development
    import smbus2
except ImportError:  # pragma: no cover - development fallback
    smbus2 = None

from .data_structures import (
    CameraFrame,
    DeviceHealth,
    I2CDeviceReading,
    RoboHATStatus,
    SensorReading,
    SerialDeviceReading,
)
from .exceptions import CommunicationError, DeviceNotFoundError, HardwareError


class RetryPolicy:
    """Exponential backoff with jitter for retry logic"""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 5.0,
        backoff_factor: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def get_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter"""
        delay = min(self.base_delay * (self.backoff_factor**attempt), self.max_delay)
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter


class I2CManager:
    """Singleton I2C bus manager with thread-safe access"""

    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.logger = logging.getLogger(__name__)
        self._bus_lock = asyncio.Lock()
        self._device_locks: Dict[int, asyncio.Lock] = {}
        self._device_health: Dict[int, DeviceHealth] = {}
        self._bus = None
        self._retry_policy = RetryPolicy()

        # I2C device registry with default addresses
        self.devices = {
            "tof_left": 0x29,
            "tof_right": 0x30,
            "power_monitor": 0x40,
            "environmental": 0x76,
            "display": 0x3C,
        }

    async def initialize(self, bus_number: int = 1):
        """Initialize I2C bus"""
        async with self._lock:
            if self._bus is None:
                try:
                    if smbus2:
                        self._bus = smbus2.SMBus(bus_number)
                        self.logger.info(f"I2C bus {bus_number} initialized")
                    else:
                        self.logger.warning("smbus2 not available, using mock")
                        self._bus = MockSMBus(bus_number)

                    # Initialize device locks and health tracking
                    for device_name, address in self.devices.items():
                        self._device_locks[address] = asyncio.Lock()
                        self._device_health[address] = DeviceHealth(f"i2c_{address:02x}")

                except Exception as e:
                    raise HardwareError(f"Failed to initialize I2C bus: {e}")

    async def cleanup(self):
        """Clean up I2C resources and release bus handles"""
        async with self._lock:
            try:
                if self._bus and hasattr(self._bus, "close"):
                    try:
                        self._bus.close()
                    except Exception as e:
                        self.logger.debug(f"I2C bus close error: {e}")
                self._bus = None
            finally:
                # Clear device locks/health to allow reinitialization
                self._device_locks.clear()
                self._device_health.clear()
        self.logger.info("I2C manager cleaned up")

    @asynccontextmanager
    async def device_access(self, address: int):
        """Async context manager for exclusive device access"""
        if address not in self._device_locks:
            self._device_locks[address] = asyncio.Lock()
            self._device_health[address] = DeviceHealth(f"i2c_{address:02x}")

        async with self._device_locks[address]:
            yield

    async def read_register(self, address: int, register: int, length: int = 1) -> List[int]:
        """Read from I2C device register with retry logic"""
        async with self.device_access(address):
            for attempt in range(self._retry_policy.max_retries + 1):
                try:
                    if length == 1:
                        data = [self._bus.read_byte_data(address, register)]
                    else:
                        data = self._bus.read_i2c_block_data(address, register, length)

                    await self._device_health[address].record_success()
                    return data

                except Exception as e:
                    await self._device_health[address].record_failure()

                    if attempt == self._retry_policy.max_retries:
                        raise CommunicationError(
                            f"Failed to read from I2C device 0x{address:02x} "
                            f"register 0x{register:02x}: {e}"
                        )

                    delay = self._retry_policy.get_delay(attempt)
                    self.logger.warning(
                        f"I2C read failed (attempt {attempt + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)

    async def write_register(self, address: int, register: int, data: Any):
        """Write to I2C device register with retry logic"""
        async with self.device_access(address):
            for attempt in range(self._retry_policy.max_retries + 1):
                try:
                    if isinstance(data, int):
                        self._bus.write_byte_data(address, register, data)
                    else:
                        self._bus.write_i2c_block_data(address, register, data)

                    await self._device_health[address].record_success()
                    return

                except Exception as e:
                    await self._device_health[address].record_failure()

                    if attempt == self._retry_policy.max_retries:
                        raise CommunicationError(
                            f"Failed to write to I2C device 0x{address:02x} "
                            f"register 0x{register:02x}: {e}"
                        )

                    delay = self._retry_policy.get_delay(attempt)
                    self.logger.warning(
                        f"I2C write failed (attempt {attempt + 1}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)

    async def scan_devices(self) -> List[int]:
        """Scan I2C bus for connected devices"""
        found_devices = []
        async with self._bus_lock:
            for address in range(0x08, 0x78):  # Valid I2C address range
                try:
                    self._bus.read_byte(address)
                    found_devices.append(address)
                except:
                    pass
        return found_devices

    def get_device_health(self, address: int) -> DeviceHealth:
        """Get health status for specific device"""
        return self._device_health.get(address, DeviceHealth(f"i2c_{address:02x}"))


class SerialManager:
    """Manager for serial/UART communications"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._connections: Dict[str, serial.Serial] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._health: Dict[str, DeviceHealth] = {}
        self._retry_policy = RetryPolicy()
        # Callbacks: async def cb(device_name: str, command: str, success: bool) -> None
        self._write_listeners: List[Callable[[str, str, bool], Any]] = []

        # Serial device configurations
        self.devices = {
            # Default serial mappings; overridden by config/hardware.yaml when present
            # RoboHAT on Pi header UART0 via stable alias /dev/serial0
            "robohat": {"port": "/dev/serial0", "baud": 115200, "timeout": 1.0},
            # GPS often appears as CDC-ACM; keep typical default
            "gps": {"port": "/dev/ttyACM1", "baud": 115200, "timeout": 1.0},
            # IMU on UART4; baud overridden by plugin/config (3000000 typical for BNO085)
            "imu": {"port": "/dev/ttyAMA4", "baud": 115200, "timeout": 0.2},
        }

    async def initialize_device(self, device_name: str, **kwargs):
        """Initialize serial device connection"""
        if device_name not in self.devices:
            raise DeviceNotFoundError(f"Unknown serial device: {device_name}")

        config = self.devices[device_name].copy()
        config.update(kwargs)

        # Warn if another configured device points to the same port (potential conflict)
        try:
            same_port = [
                name
                for name, cfg in self.devices.items()
                if name != device_name and cfg and cfg.get("port") == config.get("port")
            ]
            if same_port:
                self.logger.warning(
                    f"Serial port {config.get('port')} for '{device_name}' also configured for {same_port} — potential conflict"
                )
        except Exception:
            pass

        try:
            conn = serial.Serial(
                port=config["port"], baudrate=config["baud"], timeout=config["timeout"]
            )

            self._connections[device_name] = conn
            self._locks[device_name] = asyncio.Lock()
            self._health[device_name] = DeviceHealth(device_name)
            # Persist the effective configuration so metadata reflects reality
            try:
                self.devices[device_name] = {
                    "port": config.get("port"),
                    "baud": config.get("baud"),
                    "timeout": config.get("timeout"),
                }
            except Exception:
                pass

            self.logger.info(f"Serial device {device_name} initialized on {config['port']}")

        except Exception as e:
            raise HardwareError(f"Failed to initialize {device_name}: {e}")

    @asynccontextmanager
    async def device_access(self, device_name: str):
        """Async context manager for exclusive device access"""
        if device_name not in self._locks:
            await self.initialize_device(device_name)

        async with self._locks[device_name]:
            yield self._connections[device_name]

    async def write_command(self, device_name: str, command: str) -> bool:
        """Write command to serial device"""
        async with self.device_access(device_name) as conn:
            for attempt in range(self._retry_policy.max_retries + 1):
                try:
                    conn.write(f"{command}\n".encode())
                    conn.flush()
                    await self._health[device_name].record_success()
                    # Notify listeners (fire-and-forget)
                    await self._notify_write_listeners(device_name, command, True)
                    return True

                except Exception as e:
                    await self._health[device_name].record_failure()

                    if attempt == self._retry_policy.max_retries:
                        # Final failure, notify listeners then raise
                        await self._notify_write_listeners(device_name, command, False)
                        raise CommunicationError(f"Failed to write to {device_name}: {e}")

                    delay = self._retry_policy.get_delay(attempt)
                    await asyncio.sleep(delay)

        return False

    def add_write_listener(self, callback):
        """Register an async callback called after write attempts.

        Callback signature: async def cb(device_name: str, command: str, success: bool) -> None
        """
        self._write_listeners.append(callback)

    async def _notify_write_listeners(self, device_name: str, command: str, success: bool) -> None:
        """Notify listeners without blocking failures from propagating."""
        if not self._write_listeners:
            return
        for cb in list(self._write_listeners):
            try:
                # If callback is async, await; if sync, call in thread
                if asyncio.iscoroutinefunction(cb):
                    await cb(device_name, command, success)
                else:
                    # Run sync callback in default loop executor
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, cb, device_name, command, success)
            except Exception as e:
                self.logger.debug(f"Write listener error: {e}")

    async def read_line(self, device_name: str, timeout: float = 1.0) -> Optional[str]:
        """Read line from serial device"""
        async with self.device_access(device_name) as conn:
            try:
                conn.timeout = timeout
                raw = conn.readline()
                if not raw:
                    return None
                # Decode defensively; ignore errors and strip terminal control sequences
                try:
                    line = raw.decode(errors="ignore").strip()
                except Exception:
                    # Fallback if decode fails for any reason
                    line = "".join((chr(b) for b in raw if 32 <= b <= 126)).strip()

                # Strip common ANSI/terminal escape sequences that sometimes prefix serial output
                # Remove OSC/CSI sequences e.g. '\x1b]0;...\x1b\\' or '\x1b[...m'
                import re

                # Remove OSC sequences \x1b]...\x1b\
                line = re.sub(r"\x1b\].*?\x1b\\", "", line)
                # Remove CSI sequences \x1b[...m or similar
                line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line)

                if line:
                    await self._health[device_name].record_success()
                    return line
                return None

            except Exception as e:
                await self._health[device_name].record_failure()
                raise CommunicationError(f"Failed to read from {device_name}: {e}")

    async def cleanup(self):
        """Close all serial connections and clear state"""
        # Close connections synchronously (pyserial is blocking) but do it quickly
        for name, conn in list(self._connections.items()):
            try:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception as e:
                        self.logger.debug(f"Error closing serial connection {name}: {e}")
            finally:
                self._connections.pop(name, None)

        # Clear locks and health - leave locks to be recreated on demand
        self._locks.clear()
        self._health.clear()
        self.logger.info("Serial manager cleaned up")


class GPIOManager:
    """Manager for GPIO pin control"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._pins: Dict[int, Dict] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

        # GPIO pin assignments
        # Note: ToF right interrupt default is board-aware (Pi 5 => 8, else 12)
        self.pins = {
            "tof_left_shutdown": 22,
            "tof_right_shutdown": 23,
            "tof_left_interrupt": 6,
            "tof_right_interrupt": default_tof_right_interrupt_pin(),
            "blade_enable": 24,
            "blade_direction": 25,
        }

    async def initialize(self):
        """Initialize GPIO"""
        async with self._lock:
            if not self._initialized:
                try:
                    if GPIO:
                        GPIO.setmode(GPIO.BCM)
                        GPIO.setwarnings(False)

                    self._initialized = True
                    self.logger.info("GPIO initialized")

                except Exception as e:
                    raise HardwareError(f"Failed to initialize GPIO: {e}")

    async def setup_pin(
        self, pin: int, direction: str, pull_up_down: str = "none", initial: int = 0
    ):
        """Setup GPIO pin"""
        await self.initialize()

        async with self._lock:
            # Add short retry with backoff to mitigate transient 'GPIO busy'
            policy = RetryPolicy(max_retries=2, base_delay=0.06, max_delay=0.25, backoff_factor=2.0)
            last_err: Optional[Exception] = None
            for attempt in range(policy.max_retries + 1):
                try:
                    if GPIO:
                        gpio_dir = GPIO.OUT if direction == "output" else GPIO.IN
                        pud = {"up": GPIO.PUD_UP, "down": GPIO.PUD_DOWN, "none": GPIO.PUD_OFF}

                        # If gpio_wrapper exposes claimant info, log it for diagnostics
                        claimant = (
                            getattr(GPIO, "get_claimant", lambda p: None)(pin)
                            if hasattr(GPIO, "get_claimant")
                            else None
                        )
                        if claimant:
                            self.logger.debug(
                                f"GPIOManager.setup_pin: pin {pin} currently claimed by {claimant} before setup"
                            )

                        GPIO.setup(pin, gpio_dir, pull_up_down=pud[pull_up_down], initial=initial)

                    self._pins[pin] = {
                        "direction": direction,
                        "pull_up_down": pull_up_down,
                        "initial": initial,
                    }

                    self.logger.debug(f"GPIO pin {pin} setup as {direction}")
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    # Only retry on likely contention
                    msg = str(e).lower()
                    if attempt < policy.max_retries and ("busy" in msg or "in use" in msg):
                        delay = policy.get_delay(attempt)
                        self.logger.warning(
                            f"GPIO setup busy for pin {pin} (attempt {attempt+1}/{policy.max_retries+1}); retrying in {delay:.2f}s: {e}"
                        )
                        # Try to surface OS-level consumer info (gpioinfo) for diagnostics
                        try:
                            info = self._get_gpio_consumer_info(pin)
                            if info:
                                self.logger.warning(f"GPIO pin {pin} consumer (gpioinfo): {info}")
                        except Exception:
                            pass
                        await asyncio.sleep(delay)
                        continue
                    break

            if last_err is not None:
                raise HardwareError(f"Failed to setup GPIO pin {pin}: {last_err}")

    async def write_pin(self, pin: int, value: int):
        """Write to GPIO pin"""
        if pin not in self._pins:
            await self.setup_pin(pin, "output")

        async with self._lock:
            policy = RetryPolicy(max_retries=2, base_delay=0.05, max_delay=0.2, backoff_factor=2.0)
            last_err: Optional[Exception] = None
            for attempt in range(policy.max_retries + 1):
                try:
                    if GPIO:
                        claimant = (
                            getattr(GPIO, "get_claimant", lambda p: None)(pin)
                            if hasattr(GPIO, "get_claimant")
                            else None
                        )
                        if claimant:
                            self.logger.debug(
                                f"GPIOManager.write_pin: writing to pin {pin} claimed by {claimant}"
                            )
                        GPIO.output(pin, value)

                    self.logger.debug(f"GPIO pin {pin} set to {value}")
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    msg = str(e).lower()
                    if attempt < policy.max_retries and ("busy" in msg or "in use" in msg):
                        delay = policy.get_delay(attempt)
                        self.logger.warning(
                            f"GPIO write busy for pin {pin} (attempt {attempt+1}/{policy.max_retries+1}); retrying in {delay:.2f}s: {e}"
                        )
                        # Log OS-level consumer for diagnostics
                        try:
                            info = self._get_gpio_consumer_info(pin)
                            if info:
                                self.logger.warning(f"GPIO pin {pin} consumer (gpioinfo): {info}")
                        except Exception:
                            pass
                        await asyncio.sleep(delay)
                        continue
                    break

            if last_err is not None:
                raise HardwareError(f"Failed to write GPIO pin {pin}: {last_err}")

    def _get_gpio_consumer_info(self, pin: int) -> Optional[str]:
        """Return a short string of gpioinfo consumer for a specific BCM line, if available."""
        try:
            # Call gpioinfo and search for the given line number
            proc = subprocess.run(
                ["/usr/bin/gpioinfo"], capture_output=True, text=True, timeout=1.5
            )
            if proc.returncode != 0:
                return None
            lines = proc.stdout.splitlines()
            chip_header = None
            result = None
            for line in lines:
                if line.startswith("gpiochip"):
                    chip_header = line.strip()
                elif line.strip().startswith("line"):
                    parts = line.strip().split()
                    # Format: line <num>: "NAME" <consumer?> <dir> ... [used]
                    try:
                        num = int(parts[1].strip(":"))
                    except Exception:
                        continue
                    if num == pin:
                        # Build concise consumer info
                        consumer = None
                        # Attempt to extract quoted name and consumer token if present
                        try:
                            # The consumer appears after the quoted name; find tokens in quotes
                            import re

                            m = re.findall(r'"([^"]*)"', line)
                            if len(m) >= 2:
                                consumer = m[1]
                        except Exception:
                            pass
                        result = f"{chip_header} | {line.strip()}" if chip_header else line.strip()
                        if consumer:
                            result += f" | consumer={consumer}"
                        break
            return result
        except Exception:
            return None

    async def read_pin(self, pin: int) -> int:
        """Read from GPIO pin"""
        if pin not in self._pins:
            await self.setup_pin(pin, "input")

        async with self._lock:
            try:
                if GPIO:
                    return GPIO.input(pin)
                return 0  # Mock value

            except Exception as e:
                raise HardwareError(f"Failed to read GPIO pin {pin}: {e}")

    async def cleanup(self):
        """Reset GPIO state and release any claimed pins"""
        async with self._lock:
            try:
                if GPIO:
                    try:
                        # Prefer per-pin cleanup to avoid closing global handles in use elsewhere
                        if hasattr(GPIO, "cleanup_pins"):
                            GPIO.cleanup_pins(list(self._pins.keys()))  # type: ignore
                        elif hasattr(GPIO, "free_pin"):
                            for p in list(self._pins.keys()):
                                try:
                                    GPIO.free_pin(p)  # type: ignore
                                except Exception as e:
                                    self.logger.debug(f"GPIO free_pin error for {p}: {e}")
                        elif hasattr(GPIO, "cleanup"):
                            GPIO.cleanup()
                    except Exception as e:
                        self.logger.debug(f"GPIO cleanup error: {e}")
            finally:
                self._pins.clear()
                self._initialized = False

        self.logger.info("GPIO manager cleaned up")


class CameraManager:
    """Manager for camera access with frame buffering and optional caching"""

    def __init__(self, device_path: str = "/dev/video0", buffer_size: int = 5):
        self.logger = logging.getLogger(__name__)
        self.device_path = device_path
        self._camera = None
        self._lock = asyncio.Lock()
        self._frame_buffer: List[CameraFrame] = []
        self._buffer_size = max(1, int(buffer_size))
        self._frame_id = 0
        self._capturing = False
        self._capture_task = None
        self._first_frame_logged = False
        self._backend: str = "opencv"  # or "picamera2"
        self._picam2 = None
        # Frame caching (for cross-process consumers like Web API)
        self._cache_enabled = os.getenv("LAWNBERY_CAMERA_CACHE_ENABLED", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        cache_path_str = os.getenv(
            "LAWNBERY_CAMERA_CACHE_PATH", "/var/lib/lawnberry/camera/latest.jpg"
        )
        try:
            self._frame_cache_path = Path(cache_path_str)
        except Exception:
            self._frame_cache_path = Path("/var/lib/lawnberry/camera/latest.jpg")
        meta_override = os.getenv("LAWNBERY_CAMERA_META_PATH")
        if meta_override:
            self._frame_cache_meta_path = Path(meta_override)
        else:
            self._frame_cache_meta_path = self._frame_cache_path.with_suffix(".json")
        self._cache_interval = max(
            0.1,
            float(os.getenv("LAWNBERY_CAMERA_CACHE_INTERVAL", "0.5")),
        )
        self._last_cache_write = 0.0
        self._last_cached_frame_id = -1
        self._cache_update_task: Optional[asyncio.Task] = None

    async def initialize(self, width: int = 1920, height: int = 1080, fps: int = 30):
        """Initialize camera"""
        async with self._lock:
            try:
                # Use V4L2 backend for compatibility with Raspberry Pi rpicam stack
                if cv2 is None:
                    self.logger.warning(
                        "OpenCV (cv2) not available; attempting Picamera2 backend if present"
                    )
                    if _PICAMERA2_AVAILABLE:
                        await self._initialize_picamera2(width, height, fps)
                        return
                    raise HardwareError("Neither OpenCV nor Picamera2 available for camera capture")

                self._camera = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)
                # Prefer MJPG on Pi V4L2 for broader compatibility
                try:
                    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                    self._camera.set(cv2.CAP_PROP_FOURCC, fourcc)
                except Exception:
                    pass

                # Apply requested dimensions and fps
                try:
                    self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                    self._camera.set(cv2.CAP_PROP_FPS, fps)
                except Exception:
                    pass

                if not self._camera.isOpened():
                    raise HardwareError(f"Cannot open camera {self.device_path}")

                # Warm-up: attempt a few reads to let the pipeline settle
                read_ok = False
                for i in range(10):
                    try:
                        ok, frame = self._camera.read()
                        if ok and frame is not None:
                            read_ok = True
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.05)

                # If still not ok, try a smaller fallback resolution quickly
                if not read_ok:
                    try:
                        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        for i in range(10):
                            ok, frame = self._camera.read()
                            if ok and frame is not None:
                                read_ok = True
                                break
                            await asyncio.sleep(0.05)
                    except Exception:
                        pass

                if not read_ok:
                    # Leave device open for later attempts but log a clear warning
                    self.logger.warning(
                        f"Camera opened but no frames read from {self.device_path}; will retry during capture loop"
                    )

                    # Attempt fallback to Picamera2 if available and V4L2 isn't producing frames
                    if _PICAMERA2_AVAILABLE:
                        try:
                            # Release V4L2 handle before switching to Picamera2
                            try:
                                if self._camera is not None:
                                    self._camera.release()
                            except Exception:
                                pass
                            self._camera = None
                            await self._initialize_picamera2(width, height, fps)
                            return
                        except Exception as e2:
                            self.logger.warning(f"Picamera2 fallback failed: {e2}")

                self.logger.info(
                    f"Camera initialized: {width}x{height}@{fps}fps (device {self.device_path})"
                )

            except Exception as e:
                raise HardwareError(f"Failed to initialize camera: {e}")

    async def _initialize_picamera2(self, width: int, height: int, fps: int):
        """Initialize Picamera2 backend."""
        if not _PICAMERA2_AVAILABLE:
            raise HardwareError("Picamera2 not available")
        try:
            self._picam2 = Picamera2()
            # Video configuration: choose format with good OpenCV compatibility
            try:
                config = self._picam2.create_video_configuration(
                    main={"size": (int(width), int(height)), "format": "RGB888"},
                    controls={"FrameRate": int(fps)},
                )
            except Exception:
                # Fallback to a safe default
                config = self._picam2.create_video_configuration(
                    main={"size": (640, 480), "format": "RGB888"}
                )
            self._picam2.configure(config)
            self._backend = "picamera2"
            self.logger.info(f"Picamera2 backend initialized: {width}x{height}@{fps}fps")
        except Exception as e:
            raise HardwareError(f"Failed to initialize Picamera2: {e}")

    async def start_capture(self):
        """Start continuous frame capture"""
        if self._capturing:
            return

        self._capturing = True
        # Start underlying backend if required
        if self._backend == "picamera2" and self._picam2 is not None:
            try:
                self._picam2.start()
            except Exception as e:
                self.logger.warning(f"Picamera2 start failed: {e}")
        self._capture_task = asyncio.create_task(self._capture_loop())
        self.logger.info("Camera capture started")

    async def stop_capture(self):
        """Stop frame capture"""
        self._capturing = False
        if self._capture_task:
            await self._capture_task
            self._capture_task = None
        self.logger.info("Camera capture stopped")

    async def _capture_loop(self):
        """Continuous frame capture loop"""
        no_frame_count = 0
        last_reconfig = 0
        while self._capturing:
            try:
                if self._backend == "picamera2":
                    ret = False
                    frame = None
                    try:
                        if self._picam2 is not None:
                            arr = self._picam2.capture_array("main")
                            frame = arr
                            ret = frame is not None
                    except Exception as e:
                        self.logger.debug(f"Picamera2 capture error: {e}")
                else:
                    ret, frame = (False, None)
                    try:
                        ret, frame = self._camera.read()
                    except Exception as e:
                        # Transient read error; log once per occurrence at debug
                        self.logger.debug(f"Camera read error: {e}")

                if ret and frame is not None:
                    # Log once on the first successfully captured frame for diagnostics
                    if not self._first_frame_logged:
                        try:
                            h, w = frame.shape[:2]
                            src = self.device_path if self._backend != "picamera2" else "picamera2"
                            self.logger.info(f"First camera frame captured: {w}x{h} from {src}")
                        except Exception:
                            self.logger.info(f"First camera frame captured from {self.device_path}")
                        self._first_frame_logged = True
                    no_frame_count = 0
                    # Convert to bytes
                    if cv2 is not None:
                        # Ensure correct color order for JPEG when using Picamera2 (RGB -> BGR)
                        if self._backend == "picamera2":
                            try:
                                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                            except Exception:
                                pass
                        _, buffer = cv2.imencode(".jpg", frame)
                    else:
                        # Minimal fallback encoding (rare, since cv2 usually present); skip if unavailable
                        buffer = None
                        try:
                            import io

                            import PIL.Image as Image

                            img = Image.fromarray(frame)
                            bio = io.BytesIO()
                            img.save(bio, format="JPEG", quality=85)
                            buffer = bio.getvalue()
                        except Exception as e:
                            self.logger.error(f"JPEG encode failed: {e}")
                            buffer = b""
                    frame_data = buffer.tobytes() if hasattr(buffer, "tobytes") else (buffer or b"")

                    # Create frame object
                    camera_frame = CameraFrame(
                        timestamp=datetime.now(),
                        frame_id=self._frame_id,
                        width=frame.shape[1],
                        height=frame.shape[0],
                        format="jpeg",
                        data=frame_data,
                    )

                    # Add to buffer (keep only latest frames)
                    async with self._lock:
                        self._frame_buffer.append(camera_frame)
                        if len(self._frame_buffer) > self._buffer_size:
                            self._frame_buffer.pop(0)

                    self._frame_id += 1
                    await self._maybe_update_cache(camera_frame)

                else:
                    no_frame_count += 1
                    # After a short series of failures, attempt a gentle reconfiguration
                    if no_frame_count in (15, 60):
                        if self._backend == "picamera2":
                            # Allow Picamera2 to stabilize; reconfigure at lower res if needed later
                            if no_frame_count == 60:
                                try:
                                    # Reconfigure down to 640x480
                                    cfg = self._picam2.create_video_configuration(
                                        main={"size": (640, 480), "format": "RGB888"}
                                    )
                                    self._picam2.stop()
                                    self._picam2.configure(cfg)
                                    self._picam2.start()
                                    self.logger.warning(
                                        "Picamera2 produced no frames; adjusted resolution to 640x480"
                                    )
                                except Exception as e:
                                    self.logger.debug(f"Picamera2 reconfig failed: {e}")
                        else:
                            try:
                                # First try ensure MJPG and a modest resolution
                                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                                self._camera.set(cv2.CAP_PROP_FOURCC, fourcc)
                                if no_frame_count == 15:
                                    self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                                    self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                                else:
                                    self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                                    self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                                self.logger.warning(
                                    f"Camera produced no frames for {no_frame_count} reads; reapplied MJPG and adjusted resolution"
                                )
                            except Exception as e:
                                self.logger.debug(f"Camera reconfig attempt failed: {e}")

                await asyncio.sleep(1 / 30)  # 30fps

            except Exception as e:
                self.logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.1)

    async def get_latest_frame(self) -> Optional[CameraFrame]:
        """Get the most recent frame"""
        async with self._lock:
            return self._frame_buffer[-1] if self._frame_buffer else None

    async def get_cached_frame(self) -> Optional[CameraFrame]:
        """Load the latest cached frame from disk for cross-process access."""
        if not self._cache_enabled:
            return None

        try:
            frame_bytes = await asyncio.to_thread(self._frame_cache_path.read_bytes)
        except FileNotFoundError:
            return None
        except Exception as exc:
            self.logger.debug(f"Failed to read cached camera frame: {exc}")
            return None

        metadata: Dict[str, Any] = {}
        try:
            meta_text = await asyncio.to_thread(
                self._frame_cache_meta_path.read_text, encoding="utf-8"
            )
            metadata = json.loads(meta_text)
        except FileNotFoundError:
            metadata = {}
        except Exception as exc:
            self.logger.debug(f"Failed to read cached camera metadata: {exc}")
            metadata = {}

        timestamp_str = metadata.get("timestamp")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now()
        except Exception:
            timestamp = datetime.now()

        try:
            frame_id = int(metadata.get("frame_id", -1))
        except Exception:
            frame_id = -1
        try:
            width = int(metadata.get("width", 0))
            height = int(metadata.get("height", 0))
        except Exception:
            width, height = 0, 0
        frame_format = metadata.get("format", "jpeg")

        cache_meta = dict(metadata)
        cache_meta["source"] = "cache"

        return CameraFrame(
            timestamp=timestamp,
            frame_id=frame_id,
            width=width,
            height=height,
            format=frame_format,
            data=frame_bytes,
            metadata=cache_meta,
        )

    async def get_frame_buffer(self) -> List[CameraFrame]:
        """Get all buffered frames"""
        async with self._lock:
            return self._frame_buffer.copy()

    async def cleanup(self):
        """Stop capture and release camera device resources"""
        # Stop capture loop first
        try:
            await self.stop_capture()
        except Exception:
            # Best-effort stop
            pass

        async with self._lock:
            try:
                if self._backend == "picamera2" and self._picam2 is not None:
                    try:
                        self._picam2.stop()
                    except Exception:
                        pass
                    try:
                        self._picam2.close()
                    except Exception:
                        pass
                    self._picam2 = None
                if self._camera is not None:
                    try:
                        self._camera.release()
                    except Exception as e:
                        self.logger.debug(f"Error releasing camera: {e}")
                    self._camera = None
            finally:
                self._frame_buffer.clear()
                self._capturing = False
                self._capture_task = None
                self._first_frame_logged = False
                self._backend = "opencv"

        self.logger.info("Camera manager cleaned up")

    async def _maybe_update_cache(self, frame: CameraFrame) -> None:
        """Persist the latest frame for external consumers at a throttled rate."""
        if not self._cache_enabled:
            return

        if frame.frame_id == self._last_cached_frame_id:
            return

        now = time.monotonic()
        if (now - self._last_cache_write) < self._cache_interval:
            return

        if self._cache_update_task and not self._cache_update_task.done():
            # A write is already in flight; skip to avoid queue buildup.
            return

        self._last_cache_write = now
        self._last_cached_frame_id = frame.frame_id
        self._cache_update_task = asyncio.create_task(self._write_cache_async(frame))

    async def _write_cache_async(self, frame: CameraFrame) -> None:
        """Persist frame bytes and metadata using a background thread."""
        frame_bytes = bytes(frame.data)
        metadata = {
            "frame_id": frame.frame_id,
            "timestamp": frame.timestamp.isoformat(),
            "width": frame.width,
            "height": frame.height,
            "format": frame.format,
            "device_path": self.device_path,
            "backend": self._backend,
        }

        def _write_files() -> None:
            try:
                self._frame_cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_frame = self._frame_cache_path.parent / (self._frame_cache_path.name + ".tmp")
                with tmp_frame.open("wb") as fh:
                    fh.write(frame_bytes)
                os.replace(tmp_frame, self._frame_cache_path)

                tmp_meta = (
                    self._frame_cache_meta_path.parent
                    / (self._frame_cache_meta_path.name + ".tmp")
                )
                with tmp_meta.open("w", encoding="utf-8") as fh:
                    json.dump(metadata, fh, separators=(",", ":"))
                os.replace(tmp_meta, self._frame_cache_meta_path)
            except Exception as exc:  # pragma: no cover - best-effort cache
                self.logger.debug(f"Camera cache write failed: {exc}")

        await asyncio.to_thread(_write_files)


class MockSMBus:
    """Mock SMBus for development/testing"""

    def __init__(self, bus_number: int):
        self.bus_number = bus_number

    def read_byte_data(self, address: int, register: int) -> int:
        return random.randint(0, 255)

    def read_i2c_block_data(self, address: int, register: int, length: int) -> List[int]:
        return [random.randint(0, 255) for _ in range(length)]

    def write_byte_data(self, address: int, register: int, value: int):
        pass

    def write_i2c_block_data(self, address: int, register: int, data: List[int]):
        pass

    def read_byte(self, address: int) -> int:
        if random.random() < 0.1:  # 10% chance of device not responding
            raise OSError("Device not found")
        return random.randint(0, 255)
