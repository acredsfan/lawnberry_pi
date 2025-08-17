"""Unified GPIO wrapper supporting lgpio or RPi.GPIO.

Provides a minimal interface used by the project so the rest of the codebase
can operate on Raspberry Pi 4B and 5 without modification.
"""

from __future__ import annotations

import logging

try:  # Prefer lgpio for Raspberry Pi 5 compatibility
    import lgpio  # type: ignore
    import inspect
    import os

    # Simple in-process claim registry: pin -> claimant string
    _PIN_CLAIMS: dict[int, str] = {}

    def _discover_caller() -> str:
        try:
            # Walk stack to the first caller outside this module
            for frame_info in inspect.stack()[2:6]:
                fname = frame_info.filename
                if fname and os.path.basename(fname) != os.path.basename(__file__):
                    return os.path.splitext(os.path.basename(fname))[0]
        except Exception:
            pass
        return "unknown"

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
            claimant = _discover_caller()
            existing = _PIN_CLAIMS.get(pin)
            if existing and existing != claimant:
                logging.getLogger(__name__).warning(f"GPIO.setup: pin {pin} already claimed by {existing}; {claimant} is also attempting to claim it")

            if direction == self.OUT:
                lgpio.gpio_claim_output(self._chip, pin, initial)
            else:
                lgpio.gpio_claim_input(self._chip, pin)

            _PIN_CLAIMS[pin] = claimant

        def claim_pin(self, pin: int, claimant: str) -> None:
            """Record intent to use a pin without performing hardware ops."""
            existing = _PIN_CLAIMS.get(pin)
            if existing and existing != claimant:
                logging.getLogger(__name__).warning(f"GPIO.claim_pin: pin {pin} already claimed by {existing}; {claimant} attempting to claim")
            _PIN_CLAIMS[pin] = claimant

        def release_pin(self, pin: int) -> None:
            _PIN_CLAIMS.pop(pin, None)

        def output(self, pin: int, value: int) -> None:
            claimant = _PIN_CLAIMS.get(pin, None)
            if claimant is None:
                logging.getLogger(__name__).warning(f"GPIO.output: pin {pin} written without a recorded claimant")
            lgpio.gpio_write(self._chip, pin, value)

        def input(self, pin: int) -> int:
            return lgpio.gpio_read(self._chip, pin)

        def cleanup(self) -> None:
            lgpio.gpiochip_close(self._chip)
            # Clear all claims for this chip (best-effort)
            _PIN_CLAIMS.clear()

    GPIO = _GPIO()
    # Expose diagnostic helpers on the lgpio-based instance
    def _get_claimant(pin: int):
        return _PIN_CLAIMS.get(pin)
    def _list_claims():
        return dict(_PIN_CLAIMS)
    GPIO.get_claimant = _get_claimant  # type: ignore
    GPIO.list_claims = _list_claims  # type: ignore
except Exception:  # pragma: no cover - fallback for non-Pi environments
    try:
        import RPi.GPIO as _GPIO  # type: ignore
        import inspect
        import os

        # Simple in-process claim registry: pin -> claimant string
        _PIN_CLAIMS: dict[int, str] = {}

        def _discover_caller() -> str:
            try:
                for frame_info in inspect.stack()[2:6]:
                    fname = frame_info.filename
                    if fname and os.path.basename(fname) != os.path.basename(__file__):
                        return os.path.splitext(os.path.basename(fname))[0]
            except Exception:
                pass
            return "unknown"

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
                claimant = _discover_caller()
                existing = _PIN_CLAIMS.get(pin)
                if existing and existing != claimant:
                    logging.getLogger(__name__).warning(f"GPIO.setup: pin {pin} already claimed by {existing}; {claimant} is also attempting to claim it")
                _GPIO.setup(pin, direction, pull_up_down=pull_up_down, initial=initial)
                _PIN_CLAIMS[pin] = claimant

            def claim_pin(self, pin: int, claimant: str) -> None:
                existing = _PIN_CLAIMS.get(pin)
                if existing and existing != claimant:
                    logging.getLogger(__name__).warning(f"GPIO.claim_pin: pin {pin} already claimed by {existing}; {claimant} attempting to claim")
                _PIN_CLAIMS[pin] = claimant

            def release_pin(self, pin: int) -> None:
                _PIN_CLAIMS.pop(pin, None)

            def output(self, pin: int, value: int) -> None:
                claimant = _PIN_CLAIMS.get(pin, None)
                if claimant is None:
                    logging.getLogger(__name__).warning(f"GPIO.output: pin {pin} written without a recorded claimant")
                _GPIO.output(pin, value)

            def input(self, pin: int) -> int:
                return _GPIO.input(pin)

            def cleanup(self) -> None:
                _GPIO.cleanup()
                _PIN_CLAIMS.clear()

        # Expose diagnostic helpers on the instance
        GPIO = _GPIOWrapper()
        def _get_claimant(pin: int):
            return _PIN_CLAIMS.get(pin)
        def _list_claims():
            return dict(_PIN_CLAIMS)
        GPIO.get_claimant = _get_claimant  # type: ignore
        GPIO.list_claims = _list_claims  # type: ignore
        GPIO.claim_pin = GPIO.claim_pin  # type: ignore
        GPIO.release_pin = GPIO.release_pin  # type: ignore
    except Exception:  # pragma: no cover - no GPIO libs available
        GPIO = None
        logging.warning("No GPIO library available; running in simulation mode")
