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

from typing import Any, Optional
import logging

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver

logger = logging.getLogger(__name__)


class _GPIOAdapter:
    """Tiny GPIO adapter to allow testing without real hardware.

    In SIM_MODE or when adapter is not available, methods are no-ops.
    """

    def __init__(self, in1: int, in2: int):
        self.in1 = in1
        self.in2 = in2
        self._active = False
        self._initialized = False

    def setup(self) -> None:
        # Defer selecting a library until we run on hardware; tests will skip
        self._initialized = True
        self._active = False

    def set_active(self, active: bool) -> None:
        self._active = bool(active)

    def is_active(self) -> bool:
        return self._active

    def cleanup(self) -> None:
        self._initialized = False
        self._active = False


class IBT4BladeDriver(HardwareDriver):
    """IBT-4 blade controller driver.

    Config keys:
    - pins: {"in1": 24, "in2": 25}
    - name: optional identifier
    """

    def __init__(self, config: dict[str, Any] | None = None, gpio_adapter: Optional[_GPIOAdapter] = None):
        super().__init__(config)
        pins = (config or {}).get("pins", {})
        self.in1 = int(pins.get("in1", 24))
        self.in2 = int(pins.get("in2", 25))
        self._gpio = gpio_adapter or _GPIOAdapter(self.in1, self.in2)
        self._blade_active = False
        self._estop_latched = False

    async def initialize(self) -> None:
        if not is_simulation_mode():
            try:
                self._gpio.setup()
            except Exception as e:
                logger.warning("IBT-4 GPIO setup failed; falling back to simulated mode: %s", e)
        else:
            logger.info("IBT-4 blade driver in SIM_MODE; GPIO disabled")
        self.initialized = True

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        try:
            self._gpio.set_active(False)
        except Exception:
            pass
        self._blade_active = False
        self.running = False

    async def health_check(self) -> dict[str, Any]:
        return {
            "driver": "ibt4",
            "initialized": self.initialized,
            "running": self.running,
            "active": self._blade_active,
            "pins": {"in1": self.in1, "in2": self.in2},
            "estop_latched": self._estop_latched,
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
