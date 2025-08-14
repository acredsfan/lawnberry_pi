"""Unified GPIO wrapper supporting lgpio or RPi.GPIO.

Provides a minimal interface used by the project so the rest of the codebase
can operate on Raspberry Pi 4B and 5 without modification.
"""

from __future__ import annotations

import logging

try:  # Prefer lgpio for Raspberry Pi 5 compatibility
    import lgpio  # type: ignore

    class _GPIO:
        BCM = "BCM"  # placeholder for compatibility
        OUT = "out"
        IN = "in"
        PUD_UP = "up"
        PUD_DOWN = "down"
        PUD_OFF = "off"
        HIGH = 1
        LOW = 0

        def __init__(self) -> None:
            self._chip = lgpio.gpiochip_open(0)

        def setmode(self, mode):
            """Ignored: lgpio does not require pin numbering mode."""

        def setwarnings(self, flag: bool) -> None:
            """Ignored: provided for API compatibility."""

        def setup(self, pin: int, direction: str, pull_up_down: str = PUD_OFF, initial: int = LOW) -> None:
            if direction == self.OUT:
                lgpio.gpio_claim_output(self._chip, pin, initial)
            else:
                lgpio.gpio_claim_input(self._chip, pin)

        def output(self, pin: int, value: int) -> None:
            lgpio.gpio_write(self._chip, pin, value)

        def input(self, pin: int) -> int:
            return lgpio.gpio_read(self._chip, pin)

        def cleanup(self) -> None:
            lgpio.gpiochip_close(self._chip)

    GPIO = _GPIO()
except Exception:  # pragma: no cover - fallback for non-Pi environments
    try:
        import RPi.GPIO as _GPIO  # type: ignore

        class _GPIOWrapper:
            BCM = _GPIO.BCM
            OUT = _GPIO.OUT
            IN = _GPIO.IN
            PUD_UP = _GPIO.PUD_UP
            PUD_DOWN = _GPIO.PUD_DOWN
            PUD_OFF = _GPIO.PUD_OFF
            HIGH = _GPIO.HIGH
            LOW = _GPIO.LOW

            def setmode(self, mode) -> None:
                _GPIO.setmode(mode)

            def setwarnings(self, flag: bool) -> None:
                _GPIO.setwarnings(flag)

            def setup(self, pin: int, direction: str, pull_up_down: str = _GPIO.PUD_OFF, initial: int = _GPIO.LOW) -> None:
                _GPIO.setup(pin, direction, pull_up_down=pull_up_down, initial=initial)

            def output(self, pin: int, value: int) -> None:
                _GPIO.output(pin, value)

            def input(self, pin: int) -> int:
                return _GPIO.input(pin)

            def cleanup(self) -> None:
                _GPIO.cleanup()

        GPIO = _GPIOWrapper()
    except Exception:  # pragma: no cover - no GPIO libs available
        GPIO = None
        logging.warning("No GPIO library available; running in simulation mode")
