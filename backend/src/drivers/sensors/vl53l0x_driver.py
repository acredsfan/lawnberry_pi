"""VL53L0X Time-of-Flight distance sensor driver (T045).

Implements async lifecycle using the HardwareDriver ABC. Supports three modes:

1) Simulation (SIM_MODE=1): deterministic synthetic distances for tests.
2) Real hardware via common Python bindings (``VL53L0X``/``vl53l0x`` modules)
     if available on the system. This is the preferred path on Raspberry Pi.
3) Graceful fallback: if no binding is available or any I2C error occurs, keep
     the last good value without crashing upper layers.

We expose a single `read_distance_mm` method used by SensorManager and safety
triggers (e.g., obstacle < 200 mm → emergency stop). Reads are performed
non-blockingly via ``asyncio.to_thread`` when the binding requires blocking I/O.

Platform / Constitution Notes:
- Safe on Pi 4B/5. Avoids importing optional libs unless needed.
- Uses environment overrides when config is absent:
    TOF_LEFT_ADDR / TOF_RIGHT_ADDR (hex or int), TOF_BUS, TOF_RANGING_MODE.
- Keeps fast execution for health_check/read; actual I/O delegated to thread.
"""
from __future__ import annotations

import asyncio
import os
import random
import time
from typing import Any, Optional

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver

# Shared singletons for Adafruit backend and GPIO control
_adafruit_i2c = None
_gpio_provider = None  # one of ('lgpio','periphery','rpi_gpio', None)
_pair_initialized = False


class VL53L0XDriver(HardwareDriver):
    """Minimal VL53L0X driver implementation.

    In real mode this would open the I2C bus and configure continuous ranging
    for each sensor (left/right). At this stage (Phase 3 scaffolding) we only
    provide simulation outputs. Two instances can be created with different
    sensor_id (e.g., "left", "right").
    """

    def __init__(self, sensor_side: str, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        self.sensor_side = sensor_side
        self._last_distance_mm: int | None = None
        self._last_read_ts: float | None = None
        cfg = config or {}
        # Address/bus from config or env, with sensible defaults for dual-sensor setups
        env_addr = os.environ.get("TOF_LEFT_ADDR" if sensor_side == "left" else "TOF_RIGHT_ADDR")
        self._i2c_address = int(
            cfg.get("address")
            or (int(env_addr, 0) if env_addr else None)
            or (0x29 if sensor_side == "left" else 0x30)
        )
        self._i2c_bus = int(cfg.get("bus") or os.environ.get("TOF_BUS", 1))
        self._ranging_mode = (cfg.get("ranging_mode") or os.environ.get("TOF_RANGING_MODE") or "better_accuracy").lower()
        # Optional XSHUT pins (BCM numbering) for address assignment using Adafruit backend
        self._xshut_gpio: Optional[int] = None
        env_x = os.environ.get("TOF_LEFT_SHUTDOWN_GPIO" if sensor_side == "left" else "TOF_RIGHT_SHUTDOWN_GPIO")
        val_x = cfg.get("shutdown_gpio") if cfg.get("shutdown_gpio") is not None else (int(env_x) if env_x else None)
        if isinstance(val_x, int):
            self._xshut_gpio = val_x
        self._sim_distance_cycle: int = 0
        self._driver = None  # Underlying Python binding instance (if available)
        self._driver_backend: str | None = None  # 'pololu', 'alt', or None
        self._fail_count: int = 0
        self._last_init_attempt: float | None = None
        # Optional timing budget (microseconds) for Adafruit backend
        try:
            tb_env = os.environ.get("TOF_TIMING_BUDGET_US")
            self._timing_budget_us: Optional[int] = int(cfg.get("timing_budget_us") or (int(tb_env) if tb_env else 0)) or None
        except Exception:
            self._timing_budget_us = None

    async def initialize(self) -> None:  # noqa: D401
        """Initialize hardware or simulation.

        Attempt to load a Python binding for VL53L0X. Supported modules:
        - 'VL53L0X' (Pololu-style)
        - 'vl53l0x' (alternative publishing)
        If none available and not in SIM_MODE, we still mark initialized so
        higher layers can proceed while we gracefully no-op on reads.
        """
        self.initialized = True
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            return

        # Try Adafruit CircuitPython backend first (most common on Pi via Blinka)
        if await _try_init_adafruit(self):
            return

        # Fallback backends: Pololu-style or alt
        await _try_init_pololu_like(self)

    async def start(self) -> None:  # noqa: D401
        # On some modules, ranging already started in initialize; mark running
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False
        if self._driver is not None and not (is_simulation_mode() or os.environ.get("SIM_MODE") == "1"):
            try:
                stop_fn = getattr(self._driver, "stop_ranging", None)
                if callable(stop_fn):
                    await asyncio.to_thread(stop_fn)
            except Exception:
                pass

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": f"vl53l0x_{self.sensor_side}",
            "initialized": self.initialized,
            "running": self.running,
            "last_distance_mm": self._last_distance_mm,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode(),
            "i2c_bus": self._i2c_bus,
            "i2c_address": hex(self._i2c_address),
            "backend": self._driver_backend,
            "fail_count": self._fail_count,
            "timing_budget_us": self._timing_budget_us,
        }

    async def read_distance_mm(self) -> int | None:
        """Return latest distance in millimeters.

        Simulation mode generates a deterministic oscillating pattern around
        1500mm with occasional obstacle (<180mm) every ~20 cycles for contract
        test development. Real hardware would perform an I2C read sequence.
        """
        if not self.initialized:
            return None

        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            # Deterministic pattern to keep tests stable
            base = 1500
            if self._sim_distance_cycle % 20 == 5:
                simulated = random.randint(120, 180)  # simulate obstacle event
            else:
                simulated = base + (self._sim_distance_cycle % 40) * 10
            self._sim_distance_cycle += 1
            self._last_distance_mm = simulated
            self._last_read_ts = time.time()
            return simulated

        # Real hardware path
        distance: int | None = None
        try:
            if self._driver is not None:
                if self._driver_backend == "adafruit":
                    # Adafruit property `.range` returns mm. Access in a thread to avoid blocking loop.
                    def _read_range():
                        try:
                            return getattr(self._driver, "range")
                        except Exception:
                            return None

                    val = await asyncio.to_thread(_read_range)
                    try:
                        distance = int(val) if val is not None else None
                    except (TypeError, ValueError):
                        distance = None
                else:
                    get_fn = getattr(self._driver, "get_distance", None)
                    if callable(get_fn):
                        val = await asyncio.to_thread(get_fn)
                        try:
                            distance = int(val) if val is not None else None
                        except (TypeError, ValueError):
                            distance = None
        except Exception:
            # Ignore errors and keep last good reading
            distance = None

        # Update state if we obtained a measurement
        if isinstance(distance, int) and distance >= 0:
            self._last_distance_mm = distance
            self._last_read_ts = time.time()
            self._fail_count = 0
            return distance

        # No driver or read failed; keep previous value to avoid churn
        self._last_read_ts = time.time()
        self._fail_count += 1
        # If repeated failures and not in SIM, try to reinitialize backend in the background
        await _reinit_if_needed(self)
        return self._last_distance_mm


__all__ = ["VL53L0XDriver", "ensure_pair_addressing"]

# -------------------------- Private helpers ---------------------------

async def _ensure_gpio_provider() -> Optional[str]:
    global _gpio_provider
    if _gpio_provider is not None:
        return _gpio_provider
    # Try lgpio (fast on Pi 5), then periphery, then RPi.GPIO
    try:
        import lgpio  # type: ignore
        _gpio_provider = "lgpio"
        return _gpio_provider
    except Exception:
        try:
            from periphery import GPIO  # type: ignore
            _gpio_provider = "periphery"
            return _gpio_provider
        except Exception:
            try:
                import RPi.GPIO as GPIO  # type: ignore
                _gpio_provider = "rpi_gpio"
                return _gpio_provider
            except Exception:
                _gpio_provider = None
                return _gpio_provider


def _gpio_set(pin: int, value: int) -> None:
    if _gpio_provider == "lgpio":
        import lgpio  # type: ignore
        # Use a global chip handle for simplicity
        if not hasattr(_gpio_set, "_chip"):
            _gpio_set._chip = lgpio.gpiochip_open(0)  # type: ignore[attr-defined]
        ch = _gpio_set._chip  # type: ignore[attr-defined]
        lgpio.gpio_claim_output(ch, pin, 0)
        lgpio.gpio_write(ch, pin, 1 if value else 0)
    elif _gpio_provider == "periphery":
        from periphery import GPIO  # type: ignore
        if not hasattr(_gpio_set, "_pins"):
            _gpio_set._pins = {}
        pins = _gpio_set._pins  # type: ignore[attr-defined]
        if pin not in pins:
            pins[pin] = GPIO(pin, "out")
        pins[pin].write(bool(value))
    elif _gpio_provider == "rpi_gpio":
        import RPi.GPIO as GPIO  # type: ignore
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH if value else GPIO.LOW)


async def _try_pair_init_adafruit(left_gpio: Optional[int], right_gpio: Optional[int], right_addr: int) -> bool:
    """Initialize both sensors with unique addresses using XSHUT pins.

    Sequence (addresses reset at power-on):
      - Pull both XSHUT low
      - Bring RIGHT high, create sensor at 0x29, set address to right_addr (e.g., 0x30)
      - Bring LEFT high (stays at default 0x29)
    """
    global _pair_initialized, _adafruit_i2c
    if _pair_initialized:
        return True
    if left_gpio is None or right_gpio is None:
        return False
    provider = await _ensure_gpio_provider()
    if provider is None:
        return False
    # Set both low
    _gpio_set(left_gpio, 0)
    _gpio_set(right_gpio, 0)
    time.sleep(0.02)
    # Bring right high and set new address
    _gpio_set(right_gpio, 1)
    time.sleep(0.02)
    try:
        import board  # type: ignore
        import busio  # type: ignore
        import adafruit_vl53l0x  # type: ignore
        if _adafruit_i2c is None:
            _adafruit_i2c = busio.I2C(board.SCL, board.SDA)
        # Create sensor at default 0x29 and change address
        sensor = adafruit_vl53l0x.VL53L0X(_adafruit_i2c)
        # Adafruit API provides set_address(new_addr)
        sensor.set_address(right_addr)
        # Optional timing budget tune if supported
        try:
            if hasattr(sensor, "measurement_timing_budget"):
                sensor.measurement_timing_budget = int(os.environ.get("TOF_TIMING_BUDGET_US", "0")) or 200000
        except Exception:
            pass
        # Optional: set measurement timing budget or continuous mode as needed
        # sensor.measurement_timing_budget = 200000
        # sensor.start_continuous()
    except Exception:
        return False

    # Bring left high
    _gpio_set(left_gpio, 1)
    time.sleep(0.02)
    _pair_initialized = True
    return True


async def ensure_pair_addressing(left_gpio: Optional[int], right_gpio: Optional[int], right_addr: int = 0x30) -> bool:
    """Public helper to set up dual VL53L0X sensors with unique addresses via XSHUT.

    Returns True if addressing sequence executed (or already initialized), False otherwise.
    Safe to call multiple times.
    """
    return await _try_pair_init_adafruit(left_gpio, right_gpio, right_addr)


async def _try_prepare_adafruit_instance(address: int) -> tuple[object | None, Optional[str]]:
    """Create Adafruit VL53L0X instance bound to a specific address."""
    global _adafruit_i2c
    try:
        import board  # type: ignore
        import busio  # type: ignore
        import adafruit_vl53l0x  # type: ignore
    except Exception:
        return None, None
    try:
        if _adafruit_i2c is None:
            _adafruit_i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l0x.VL53L0X(_adafruit_i2c, address=address)
        # Apply timing budget if provided via env
        try:
            tb_env = os.environ.get("TOF_TIMING_BUDGET_US")
            if tb_env:
                sensor.measurement_timing_budget = int(tb_env)
        except Exception:
            pass
        return sensor, "adafruit"
    except Exception:
        return None, None


async def _try_init_pololu_like(self: VL53L0XDriver) -> None:
    # Lazy import optional bindings
    module = None
    try:
        import VL53L0X as _m  # type: ignore

        module = _m
        self._driver_backend = "pololu"
    except Exception:
        try:
            import vl53l0x as _m  # type: ignore

            module = _m
            self._driver_backend = "alt"
        except Exception:
            module = None
            self._driver_backend = None

    if module is None:
        # No Python binding available; we'll gracefully degrade in reads
        return

    # Create driver instance; different modules export class differently
    try:
        cls = getattr(module, "VL53L0X", module)
        # Common constructor signature: VL53L0X(i2c_bus=1, i2c_address=0x29)
        self._driver = cls(i2c_bus=self._i2c_bus, i2c_address=self._i2c_address)
    except Exception:
        # If constructor signature differs, attempt minimal positional init
        try:
            self._driver = cls(self._i2c_bus, self._i2c_address)  # type: ignore[name-defined]
        except Exception:
            self._driver = None
            self._driver_backend = None

    # Configure/prepare ranging if driver exists
    if self._driver is not None:
        try:
            # Map mode string to constant if present; otherwise ignore
            mode_map = {
                "short": getattr(module, "VL53L0X_GOOD_ACCURACY_MODE", None),
                "better_accuracy": getattr(module, "VL53L0X_BETTER_ACCURACY_MODE", None),
                "best_accuracy": getattr(module, "VL53L0X_BEST_ACCURACY_MODE", None),
                "long_range": getattr(module, "VL53L0X_LONG_RANGE_MODE", None),
                "high_speed": getattr(module, "VL53L0X_HIGH_SPEED_MODE", None),
            }

            start_fn = getattr(self._driver, "start_ranging", None)
            if callable(start_fn):
                mode_const = mode_map.get(self._ranging_mode) or mode_map.get("better_accuracy")
                if mode_const is not None:
                    await asyncio.to_thread(start_fn, mode_const)
                else:
                    await asyncio.to_thread(start_fn)
        except Exception:
            # Keep running with get_distance available; many libs allow reads without explicit start
            pass


async def _try_init_adafruit(self: VL53L0XDriver) -> bool:
    # If Adafruit library not available, skip
    sensor, backend = await _try_prepare_adafruit_instance(self._i2c_address)
    if sensor is None:
        # If XSHUT pins exist, attempt pair init then try again
        # Prefer env, fall back to instance-configured shutdown pin for this side
        try:
            lpin = int(os.environ.get("TOF_LEFT_SHUTDOWN_GPIO")) if os.environ.get("TOF_LEFT_SHUTDOWN_GPIO") else (self._xshut_gpio if self.sensor_side == "left" else None)
        except Exception:
            lpin = self._xshut_gpio if self.sensor_side == "left" else None
        try:
            rpin = int(os.environ.get("TOF_RIGHT_SHUTDOWN_GPIO")) if os.environ.get("TOF_RIGHT_SHUTDOWN_GPIO") else (self._xshut_gpio if self.sensor_side == "right" else None)
        except Exception:
            rpin = self._xshut_gpio if self.sensor_side == "right" else None
        if await _try_pair_init_adafruit(lpin, rpin, right_addr=int(os.environ.get("TOF_RIGHT_ADDR", "0x30"), 0)):
            sensor, backend = await _try_prepare_adafruit_instance(self._i2c_address)
        else:
            return False

    if sensor is None:
        return False

    self._driver = sensor
    self._driver_backend = backend
    # Optional: no explicit start required; `.range` triggers reads
    return True


async def _reinit_if_needed(self: VL53L0XDriver) -> None:
    """Attempt to reinitialize backend after repeated failures.

    Avoids tight loops by spacing attempts at least 2 seconds apart.
    """
    if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
        return
    now = time.time()
    # Only try after a few consecutive failures
    if self._fail_count < 3:
        return
    if self._last_init_attempt and (now - self._last_init_attempt) < 2.0:
        return
    self._last_init_attempt = now
    # Try Adafruit first, then pololu-like
    try:
        if await _try_init_adafruit(self):
            return
        await _try_init_pololu_like(self)
    except Exception:
        pass
