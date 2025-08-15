"""Hardware managers for different interface types"""

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import cv2
import numpy as np
import serial

# Raspberry Pi 4B/5 compatibility is provided via gpio_wrapper
from .gpio_wrapper import GPIO

try:  # Hardware I2C library may be unavailable during development
    import smbus2
except ImportError:  # pragma: no cover - development fallback
    smbus2 = None

from .data_structures import (
    CameraFrame,
    DeviceHealth,
    GPIOReading,
    I2CDeviceReading,
    RoboHATStatus,
    SensorReading,
    SerialDeviceReading,
)
from .exceptions import (
    CommunicationError,
    DeviceBusyError,
    DeviceNotFoundError,
    DeviceTimeoutError,
    HardwareError,
)


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

    async def write_register(self, address: int, register: int, data: int | List[int]):
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
            "robohat": {"port": "/dev/ttyACM1", "baud": 115200, "timeout": 1.0},
            "gps": {"port": "/dev/ttyACM0", "baud": 38400, "timeout": 1.0},
            "imu": {"port": "/dev/ttyAMA4", "baud": 3000000, "timeout": 0.1},
        }

    async def initialize_device(self, device_name: str, **kwargs):
        """Initialize serial device connection"""
        if device_name not in self.devices:
            raise DeviceNotFoundError(f"Unknown serial device: {device_name}")

        config = self.devices[device_name].copy()
        config.update(kwargs)

        try:
            conn = serial.Serial(
                port=config["port"], baudrate=config["baud"], timeout=config["timeout"]
            )

            self._connections[device_name] = conn
            self._locks[device_name] = asyncio.Lock()
            self._health[device_name] = DeviceHealth(device_name)

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
                line = conn.readline().decode().strip()
                if line:
                    await self._health[device_name].record_success()
                    return line
                return None

            except Exception as e:
                await self._health[device_name].record_failure()
                raise CommunicationError(f"Failed to read from {device_name}: {e}")


class GPIOManager:
    """Manager for GPIO pin control"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._pins: Dict[int, Dict] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

        # GPIO pin assignments
        self.pins = {
            "tof_left_shutdown": 22,
            "tof_right_shutdown": 23,
            "tof_left_interrupt": 6,
            "tof_right_interrupt": 12,
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
            try:
                if GPIO:
                    gpio_dir = GPIO.OUT if direction == "output" else GPIO.IN
                    pud = {"up": GPIO.PUD_UP, "down": GPIO.PUD_DOWN, "none": GPIO.PUD_OFF}

                    GPIO.setup(pin, gpio_dir, pull_up_down=pud[pull_up_down], initial=initial)

                self._pins[pin] = {
                    "direction": direction,
                    "pull_up_down": pull_up_down,
                    "initial": initial,
                }

                self.logger.debug(f"GPIO pin {pin} setup as {direction}")

            except Exception as e:
                raise HardwareError(f"Failed to setup GPIO pin {pin}: {e}")

    async def write_pin(self, pin: int, value: int):
        """Write to GPIO pin"""
        if pin not in self._pins:
            await self.setup_pin(pin, "output")

        async with self._lock:
            try:
                if GPIO:
                    GPIO.output(pin, value)

                self.logger.debug(f"GPIO pin {pin} set to {value}")

            except Exception as e:
                raise HardwareError(f"Failed to write GPIO pin {pin}: {e}")

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


class CameraManager:
    """Manager for camera access with frame buffering"""

    def __init__(self, device_path: str = "/dev/video0"):
        self.logger = logging.getLogger(__name__)
        self.device_path = device_path
        self._camera = None
        self._lock = asyncio.Lock()
        self._frame_buffer: List[CameraFrame] = []
        self._buffer_size = 5
        self._frame_id = 0
        self._capturing = False
        self._capture_task = None

    async def initialize(self, width: int = 1920, height: int = 1080, fps: int = 30):
        """Initialize camera"""
        async with self._lock:
            try:
                # Use V4L2 backend for compatibility with Raspberry Pi rpicam stack
                self._camera = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)
                self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self._camera.set(cv2.CAP_PROP_FPS, fps)

                if not self._camera.isOpened():
                    raise HardwareError(f"Cannot open camera {self.device_path}")

                self.logger.info(f"Camera initialized: {width}x{height}@{fps}fps")

            except Exception as e:
                raise HardwareError(f"Failed to initialize camera: {e}")

    async def start_capture(self):
        """Start continuous frame capture"""
        if self._capturing:
            return

        self._capturing = True
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
        while self._capturing:
            try:
                ret, frame = self._camera.read()
                if ret:
                    # Convert to bytes
                    _, buffer = cv2.imencode(".jpg", frame)
                    frame_data = buffer.tobytes()

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

                await asyncio.sleep(1 / 30)  # 30fps

            except Exception as e:
                self.logger.error(f"Frame capture error: {e}")
                await asyncio.sleep(0.1)

    async def get_latest_frame(self) -> Optional[CameraFrame]:
        """Get the most recent frame"""
        async with self._lock:
            return self._frame_buffer[-1] if self._frame_buffer else None

    async def get_frame_buffer(self) -> List[CameraFrame]:
        """Get all buffered frames"""
        async with self._lock:
            return self._frame_buffer.copy()


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
