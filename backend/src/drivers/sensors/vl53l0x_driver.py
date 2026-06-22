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
import logging
import os
import random
import time
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver

# VL53L0X out-of-range sentinel: the sensor returns exactly 8190 mm when a
# measurement is invalid or the target is beyond measurement range (VCSEL period
# pre-range limit exceeded).  This value must never be treated as a real distance
# — it must be filtered to None before reaching obstacle-detection logic.
TOF_SENSOR_MAX_VALID_MM: int = 8190

# Shared singletons for Adafruit backend and GPIO control
_adafruit_i2c = None
_gpio_provider = None  # one of ('lgpio','periphery','rpi_gpio', None)
_pair_initialized = False
logger = logging.getLogger(__name__)
_XSHUT_RESET_DELAY_S = 0.05
_XSHUT_BOOT_DELAY_S = 0.10
_XSHUT_PAIR_INIT_ATTEMPTS = 3


class VL53L0XDriver(HardwareDriver):
    """VL53L0X Time-of-Flight distance sensor driver.

    Supports two physical sensors (left/right) using separate I2C addresses.
    On real hardware, attempts Adafruit CircuitPython backend first, then
    Pololu-style bindings. Uses XSHUT GPIO pins for address assignment when
    both sensors share the same default address at power-on.

    Two instances can be created with different sensor_side (``"left"`` or
    ``"right"``). Address assignment is coordinated via module-level state.
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
        self._ranging_mode = (
            cfg.get("ranging_mode") or os.environ.get("TOF_RANGING_MODE") or "better_accuracy"
        ).lower()
        # Optional XSHUT pins (BCM numbering) for address assignment using Adafruit backend
        self._xshut_gpio: int | None = None
        env_x = os.environ.get(
            "TOF_LEFT_SHUTDOWN_GPIO" if sensor_side == "left" else "TOF_RIGHT_SHUTDOWN_GPIO"
        )
        val_x = (
            cfg.get("shutdown_gpio")
            if cfg.get("shutdown_gpio") is not None
            else (int(env_x) if env_x else None)
        )
        if isinstance(val_x, int):
            self._xshut_gpio = val_x
        self._sim_distance_cycle: int = 0
        self._driver = None  # Underlying Python binding instance (if available)
        self._driver_backend: str | None = None  # 'pololu', 'alt', or None
        self._fail_count: int = 0
        self._last_init_attempt: float | None = None
        self._last_error: str | None = None
        # Optional timing budget (microseconds) for Adafruit backend
        try:
            tb_env = os.environ.get("TOF_TIMING_BUDGET_US")
            self._timing_budget_us: int | None = (
                int(cfg.get("timing_budget_us") or (int(tb_env) if tb_env else 0)) or None
            )
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
        if is_simulation_mode():
            self.initialized = True
            return

        # Try Adafruit CircuitPython backend first (most common on Pi via Blinka)
        if await _try_init_adafruit(self):
            self.initialized = True
            return

        # Fallback backends: Pololu-style or alt
        self.initialized = await _try_init_pololu_like(self)

    async def start(self) -> None:  # noqa: D401
        # On some modules, ranging already started in initialize; mark running
        self.running = is_simulation_mode() or self._driver is not None

    async def stop(self) -> None:  # noqa: D401
        self.running = False
        if self._driver is not None and not is_simulation_mode():
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
            "last_error": self._last_error,
        }

    async def read_distance_mm(self) -> int | None:
        """Return latest distance in millimeters.

        Simulation mode generates a deterministic oscillating pattern around
        1500mm with occasional obstacle (<180mm) every ~20 cycles for contract
        test development. Real hardware would perform an I2C read sequence.
        """
        if not self.initialized:
            return None

        if is_simulation_mode():
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
                            return self._driver.range
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

        # VL53L0X emits TOF_SENSOR_MAX_VALID_MM (8190 mm) as a sentinel for
        # "out of range / measurement invalid".  Discard it — do NOT cache it
        # as a valid distance and do NOT treat it as a clear-path indicator.
        # Increment fail_count so repeated sentinels can trigger re-init.
        if isinstance(distance, int) and distance >= TOF_SENSOR_MAX_VALID_MM:
            self._last_read_ts = time.time()
            self._fail_count += 1
            return None

        # Update state if we obtained a valid in-range measurement
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


__all__ = ["VL53L0XDriver", "ensure_pair_addressing", "TOF_SENSOR_MAX_VALID_MM"]

# -------------------------- Private helpers ---------------------------


async def _ensure_gpio_provider() -> str | None:
    global _gpio_provider
    if _gpio_provider is not None:
        return _gpio_provider
    # Try lgpio (fast on Pi 5), then periphery, then RPi.GPIO
    try:
        import lgpio as _lgpio  # noqa: F401
        _gpio_provider = "lgpio"
        return _gpio_provider
    except Exception:
        pass
    try:
        import periphery as _periphery  # noqa: F401
        _gpio_provider = "periphery"
        return _gpio_provider
    except Exception:
        pass
    try:
        import RPi.GPIO as _rpi_gpio  # noqa: F401
        _gpio_provider = "rpi_gpio"
        return _gpio_provider
    except Exception:
        pass
    import logging as _log
    _log.getLogger(__name__).warning(
        "No GPIO library available (lgpio/periphery/RPi.GPIO). VL53L0X XSHUT pair-init will not work."
    )
    _gpio_provider = None
    return None


# Module-level GPIO state singletons — safer than function-attribute caching.
_lgpio_chip: Any = None
_lgpio_claimed_pins: set[int] = set()
_periphery_pins: dict[int, Any] = {}


def _gpio_set(pin: int, value: int) -> None:
    global _lgpio_chip, _lgpio_claimed_pins, _periphery_pins
    if _gpio_provider == "lgpio":
        import lgpio  # type: ignore

        if _lgpio_chip is None:
            _lgpio_chip = lgpio.gpiochip_open(0)
        if pin not in _lgpio_claimed_pins:
            lgpio.gpio_claim_output(_lgpio_chip, pin, 1 if value else 0)
            _lgpio_claimed_pins.add(pin)
        lgpio.gpio_write(_lgpio_chip, pin, 1 if value else 0)
    elif _gpio_provider == "periphery":
        from periphery import GPIO  # type: ignore

        if pin not in _periphery_pins:
            _periphery_pins[pin] = GPIO(pin, "out")
        _periphery_pins[pin].write(bool(value))
    elif _gpio_provider == "rpi_gpio":
        import RPi.GPIO as GPIO  # type: ignore

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH if value else GPIO.LOW)


async def _try_pair_init_adafruit(
    left_gpio: int | None, right_gpio: int | None, right_addr: int
) -> bool:
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
    success = False
    last_error: Exception | None = None
    for attempt in range(1, _XSHUT_PAIR_INIT_ATTEMPTS + 1):
        try:
            # Set both low, then bring only the right sensor up at the default
            # address so it can be moved to the configured secondary address.
            _gpio_set(left_gpio, 0)
            _gpio_set(right_gpio, 0)
            await asyncio.sleep(_XSHUT_RESET_DELAY_S)
            _gpio_set(right_gpio, 1)
            await asyncio.sleep(_XSHUT_BOOT_DELAY_S)

            import adafruit_vl53l0x  # type: ignore
            import board  # type: ignore
            import busio  # type: ignore

            if _adafruit_i2c is None:
                _adafruit_i2c = busio.I2C(board.SCL, board.SDA)
            _i2c = _adafruit_i2c
            _raddr = right_addr

            def _do_pair_init(i2c: object = _i2c, raddr: int = _raddr) -> object:
                s = adafruit_vl53l0x.VL53L0X(i2c)
                s.set_address(raddr)
                try:
                    if hasattr(s, "measurement_timing_budget"):
                        tb = int(os.environ.get("TOF_TIMING_BUDGET_US", "0")) or 66000
                        s.measurement_timing_budget = tb
                except Exception as exc:
                    logger.debug("VL53L0X pair timing budget setup failed: %s", exc)
                return s

            await asyncio.to_thread(_do_pair_init)
            _gpio_set(left_gpio, 1)
            await asyncio.sleep(_XSHUT_BOOT_DELAY_S)
            success = True
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "VL53L0X XSHUT pair init attempt %s/%s failed: %s",
                attempt,
                _XSHUT_PAIR_INIT_ATTEMPTS,
                exc,
            )
            for pin in (left_gpio, right_gpio):
                try:
                    _gpio_set(pin, 1)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Failed to release VL53L0X XSHUT GPIO %s high after init failure: %s",
                        pin,
                        cleanup_exc,
                    )
            await asyncio.sleep(_XSHUT_BOOT_DELAY_S)

    if not success and last_error is not None:
        logger.warning("VL53L0X XSHUT pair init failed: %s", last_error)
    _pair_initialized = success

    if not success:
        return False
    return True


async def ensure_pair_addressing(
    left_gpio: int | None, right_gpio: int | None, right_addr: int = 0x30
) -> bool:
    """Public helper to set up dual VL53L0X sensors with unique addresses via XSHUT.

    Returns True if addressing sequence executed (or already initialized), False otherwise.
    Safe to call multiple times.
    """
    return await _try_pair_init_adafruit(left_gpio, right_gpio, right_addr)


async def _try_prepare_adafruit_instance(
    address: int, timing_budget_us: int | None = None
) -> tuple[object | None, str | None, str | None]:
    """Create Adafruit VL53L0X instance bound to a specific address."""
    global _adafruit_i2c
    try:
        import adafruit_vl53l0x  # type: ignore
        import board  # type: ignore
        import busio  # type: ignore
    except Exception as exc:
        return None, None, str(exc)
    try:
        if _adafruit_i2c is None:
            _adafruit_i2c = busio.I2C(board.SCL, board.SDA)
        _i2c = _adafruit_i2c
        _addr = address
        _tb_env = os.environ.get("TOF_TIMING_BUDGET_US")
        _tb = timing_budget_us

        def _do_init() -> object:
            s = adafruit_vl53l0x.VL53L0X(_i2c, address=_addr)
            try:
                tb = _tb or (int(_tb_env) if _tb_env else None)
                if tb:
                    s.measurement_timing_budget = int(tb)
            except Exception as exc:
                logger.debug("VL53L0X timing budget setup failed: %s", exc)
            return s

        sensor = await asyncio.to_thread(_do_init)
        return sensor, "adafruit", None
    except Exception as exc:
        return None, None, str(exc)


async def _try_init_pololu_like(self: VL53L0XDriver) -> bool:
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
        if not self._last_error:
            self._last_error = "No VL53L0X Python binding available"
        return False

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
            self._last_error = "Failed to create VL53L0X driver instance"
            return False

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
        self._last_error = None
        return True
    self._last_error = "VL53L0X driver instance unavailable"
    return False


async def _try_init_adafruit(self: VL53L0XDriver) -> bool:
    # If Adafruit library not available, skip
    sensor, backend, error = await _try_prepare_adafruit_instance(
        self._i2c_address, self._timing_budget_us
    )
    if sensor is None:
        if error:
            self._last_error = error
        # If XSHUT pins exist, attempt pair init then try again
        # Prefer env, fall back to instance-configured shutdown pin for this side
        try:
            lpin = (
                int(os.environ.get("TOF_LEFT_SHUTDOWN_GPIO"))
                if os.environ.get("TOF_LEFT_SHUTDOWN_GPIO")
                else (self._xshut_gpio if self.sensor_side == "left" else None)
            )
        except Exception:
            lpin = self._xshut_gpio if self.sensor_side == "left" else None
        try:
            rpin = (
                int(os.environ.get("TOF_RIGHT_SHUTDOWN_GPIO"))
                if os.environ.get("TOF_RIGHT_SHUTDOWN_GPIO")
                else (self._xshut_gpio if self.sensor_side == "right" else None)
            )
        except Exception:
            rpin = self._xshut_gpio if self.sensor_side == "right" else None
        if await _try_pair_init_adafruit(
            lpin, rpin, right_addr=int(os.environ.get("TOF_RIGHT_ADDR", "0x30"), 0)
        ):
            sensor, backend, error = await _try_prepare_adafruit_instance(
                self._i2c_address, self._timing_budget_us
            )
            if sensor is None and error:
                self._last_error = error
        else:
            return False

    if sensor is None:
        if error:
            self._last_error = error
        return False

    self._driver = sensor
    self._driver_backend = backend
    self._last_error = None
    # Optional: no explicit start required; `.range` triggers reads
    return True


async def _reinit_if_needed(self: VL53L0XDriver) -> None:
    """Attempt to reinitialize backend after repeated failures.

    Avoids tight loops by spacing attempts at least 2 seconds apart.
    """
    if is_simulation_mode():
        return
    now = time.time()
    # Only try after a few consecutive failures
    if self._fail_count < 3:
        return
    if self._last_init_attempt and (now - self._last_init_attempt) < 2.0:
        return
    self._last_init_attempt = now
    previous_driver = self._driver
    previous_backend = self._driver_backend
    previous_initialized = self.initialized
    previous_running = self.running
    # Try Adafruit first, then pololu-like
    try:
        if await _try_init_adafruit(self):
            self.initialized = True
            self.running = True
            return
        ok = await _try_init_pololu_like(self)
        if ok:
            self.initialized = True
            self.running = True
            return
    except Exception as exc:
        self._last_error = str(exc)

    if previous_driver is not None:
        self._driver = previous_driver
        self._driver_backend = previous_backend
        self.initialized = previous_initialized
        self.running = previous_running
        self._last_error = f"Reinit failed; preserving existing backend {previous_backend}"
        return

    self.initialized = False
    self.running = False
