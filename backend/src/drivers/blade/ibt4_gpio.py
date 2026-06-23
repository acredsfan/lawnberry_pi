"""
IBT-4 blade controller using Raspberry Pi GPIO 24/25.

Design goals:
- Safe defaults: blade off unless explicitly enabled
- SIM_MODE support: no GPIO access, simulate state
- Pi 4B/5 compatibility: read pin mapping from spec if provided, default to 24/25
- Respect emergency stop by exposing a local latch to be set by safety layer

This module is intentionally minimal and side-effect free for tests.
Hardware access is encapsulated behind a tiny adapter that can be stubbed.
"""

from __future__ import annotations

import logging
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver

logger = logging.getLogger(__name__)


class _GPIOAdapter:
    """Tiny GPIO adapter to allow testing without real hardware."""

    def __init__(self, in1: int, in2: int):
        self.in1 = in1
        self.in2 = in2
        self._active = False
        self._initialized = False
        self._chip = None
        self._lines: list[Any] = []

    def setup(self) -> None:
        try:
            import lgpio  # type: ignore
        except Exception as exc:
            raise RuntimeError("lgpio is required for IBT-4 GPIO blade control") from exc

        chip = lgpio.gpiochip_open(0)
        try:
            for gpio in (self.in1, self.in2):
                lgpio.gpio_claim_output(chip, gpio, 0)
                lgpio.gpio_write(chip, gpio, 0)
        except Exception:
            try:
                lgpio.gpiochip_close(chip)
            except Exception:
                pass
            raise
        self._chip = chip
        self._lines = [self.in1, self.in2]
        self._initialized = True
        self._active = False

    def set_active(self, active: bool) -> None:
        if self._chip is not None:
            import lgpio  # type: ignore

            # Forward-only blade operation: IN1 high, IN2 low. Off is both low.
            lgpio.gpio_write(self._chip, self.in1, 1 if active else 0)
            lgpio.gpio_write(self._chip, self.in2, 0)
        self._active = bool(active)

    def is_active(self) -> bool:
        return self._active

    def cleanup(self) -> None:
        if self._chip is not None:
            try:
                self.set_active(False)
                import lgpio  # type: ignore

                for gpio in self._lines:
                    try:
                        lgpio.gpio_free(self._chip, gpio)
                    except Exception:
                        pass
                lgpio.gpiochip_close(self._chip)
            finally:
                self._chip = None
                self._lines = []
        self._initialized = False
        self._active = False


class IBT4BladeDriver(HardwareDriver):
    """IBT-4 blade controller driver.

    Config keys:
    - pins: {"in1": 24, "in2": 25}
    - name: optional identifier
    """

    def __init__(
        self, config: dict[str, Any] | None = None, gpio_adapter: _GPIOAdapter | None = None
    ):
        super().__init__(config)
        pins = (config or {}).get("pins", {})
        self.in1 = int(pins.get("in1", 24))
        self.in2 = int(pins.get("in2", 25))
        self._gpio = gpio_adapter or _GPIOAdapter(self.in1, self.in2)
        self._blade_active = False
        self._estop_latched = False
        self._offline_reason: str | None = None

    async def initialize(self) -> None:
        if is_simulation_mode():
            logger.info("IBT-4 blade driver in SIM_MODE; GPIO disabled")
        else:
            try:
                self._gpio.setup()
            except Exception as e:
                self.initialized = False
                self._offline_reason = str(e)
                logger.error("IBT-4 GPIO setup failed: %s", e)
                raise
        self.initialized = True
        self._offline_reason = None

    async def start(self) -> None:
        if not self.initialized:
            raise RuntimeError(self._offline_reason or "IBT-4 blade driver is not initialized")
        await self.set_active(False)
        self.running = True

    async def stop(self) -> None:
        try:
            self._gpio.set_active(False)
        except Exception:
            pass
        self._blade_active = False
        self.running = False
        if not is_simulation_mode():
            self._gpio.cleanup()

    async def health_check(self) -> dict[str, Any]:
        return {
            "driver": "ibt4",
            "initialized": self.initialized,
            "running": self.running,
            "active": self._blade_active,
            "pins": {"in1": self.in1, "in2": self.in2},
            "estop_latched": self._estop_latched,
            "offline_reason": self._offline_reason,
        }

    async def set_estop(self, active: bool) -> None:
        self._estop_latched = bool(active)
        if active:
            await self.set_active(False)

    async def set_active(self, active: bool) -> bool:
        """Engage/disengage the blade.

        Returns True on success; respects E-stop latch.
        """
        if not self.initialized:
            return False
        if self._estop_latched and active:
            logger.warning("Blade engagement blocked by E-stop latch")
            return False
        try:
            self._gpio.set_active(bool(active))
            self._blade_active = bool(active)
            return True
        except Exception as e:
            logger.error("Failed to set blade state: %s", e)
            return False
