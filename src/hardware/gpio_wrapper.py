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
            # Defer opening the chip until first real use to avoid failures during import/startup
            self._chip = None
            self._failed_open_logged = False

        def _ensure_chip(self) -> bool:
            """Ensure gpiochip handle is open. Returns True on success, False otherwise."""
            if self._chip is not None:
                return True
            try:
                self._chip = lgpio.gpiochip_open(0)
                return True
            except Exception as e:
                if not self._failed_open_logged:
                    logging.getLogger(__name__).error(
                        "GPIO: can not open /dev/gpiochip0: %s. Check group membership (gpio) and systemd DeviceAllow.",
                        e,
                    )
                    self._failed_open_logged = True
                return False

        def _reopen_on_unknown_handle(self, exc: Exception) -> bool:
            """If the exception suggests an invalid/unknown handle, reopen the chip.
            Returns True if reopened, False otherwise.
            """
            msg = str(exc).lower()
            if "unknown handle" in msg or "bad handle" in msg or "invalid handle" in msg:
                logging.getLogger(__name__).warning("GPIO: detected unknown/bad handle; reopening chip 0 and retrying")
                try:
                    # Best-effort close before reopen
                    try:
                        if self._chip is not None:
                            lgpio.gpiochip_close(self._chip)
                    except Exception:
                        pass
                    self._chip = None
                    if not self._ensure_chip():
                        return False
                    return True
                except Exception as e:
                    logging.getLogger(__name__).error(f"GPIO: failed to reopen chip after unknown handle: {e}")
            return False

        def setmode(self, mode):
            """Ignored: lgpio does not require pin numbering mode."""

        def setwarnings(self, flag: bool) -> None:
            """Ignored: provided for API compatibility."""

        def setup(self, pin: int, direction: str, pull_up_down: str = PUD_OFF, initial: int = LOW) -> None:
            claimant = _discover_caller()
            existing = _PIN_CLAIMS.get(pin)
            if existing and existing != claimant:
                logging.getLogger(__name__).warning(f"GPIO.setup: pin {pin} already claimed by {existing}; {claimant} is also attempting to claim it")

            # Ensure chip is open and attempt the claim, retry once on unknown handle
            if not self._ensure_chip():
                raise RuntimeError("GPIO chip unavailable (/dev/gpiochip0 open failed)")
            try:
                if direction == self.OUT:
                    lgpio.gpio_claim_output(self._chip, pin, initial)
                else:
                    lgpio.gpio_claim_input(self._chip, pin)
            except Exception as e:
                if self._reopen_on_unknown_handle(e):
                    if direction == self.OUT:
                        lgpio.gpio_claim_output(self._chip, pin, initial)
                    else:
                        lgpio.gpio_claim_input(self._chip, pin)
                else:
                    raise

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
            # Ensure chip open and write, retry once on unknown handle
            if not self._ensure_chip():
                raise RuntimeError("GPIO chip unavailable (/dev/gpiochip0 open failed)")
            try:
                lgpio.gpio_write(self._chip, pin, value)
            except Exception as e:
                if self._reopen_on_unknown_handle(e):
                    lgpio.gpio_write(self._chip, pin, value)
                else:
                    raise

        def input(self, pin: int) -> int:
            # Ensure chip open and read, retry once on unknown handle
            if not self._ensure_chip():
                raise RuntimeError("GPIO chip unavailable (/dev/gpiochip0 open failed)")
            try:
                return lgpio.gpio_read(self._chip, pin)
            except Exception as e:
                if self._reopen_on_unknown_handle(e):
                    return lgpio.gpio_read(self._chip, pin)
                else:
                    raise

        def free_pin(self, pin: int) -> None:
            """Free a previously claimed pin without closing the chip."""
            try:
                if pin in _PIN_CLAIMS:
                    if not self._ensure_chip():
                        raise RuntimeError("GPIO chip unavailable (/dev/gpiochip0 open failed)")
                    try:
                        lgpio.gpio_free(self._chip, pin)
                    except Exception as e:
                        if not self._reopen_on_unknown_handle(e):
                            raise
                        lgpio.gpio_free(self._chip, pin)
            finally:
                _PIN_CLAIMS.pop(pin, None)

        def cleanup_pins(self, pins: list[int]) -> None:
            for p in pins:
                try:
                    self.free_pin(p)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"GPIO.cleanup_pins: failed to free pin {p}: {e}")

        def cleanup(self) -> None:
            """Free all claimed pins but keep the chip open to avoid 'unknown handle' later."""
            try:
                self.cleanup_pins(list(_PIN_CLAIMS.keys()))
            finally:
                _PIN_CLAIMS.clear()

        def close(self) -> None:
            """Close the underlying chip; use sparingly (typically at process shutdown)."""
            try:
                try:
                    self.cleanup()
                finally:
                    if self._chip is not None:
                        lgpio.gpiochip_close(self._chip)
            finally:
                self._chip = None

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
                # Prefer per-pin cleanup to avoid side effects on unrelated pins
                pins = list(_PIN_CLAIMS.keys())
                try:
                    if pins:
                        _GPIO.cleanup(pins)
                    else:
                        _GPIO.cleanup()
                finally:
                    _PIN_CLAIMS.clear()

            def free_pin(self, pin: int) -> None:
                try:
                    _GPIO.cleanup(pin)
                except Exception:
                    pass
                finally:
                    _PIN_CLAIMS.pop(pin, None)

            def cleanup_pins(self, pins: list[int]) -> None:
                try:
                    if pins:
                        _GPIO.cleanup(pins)
                finally:
                    for p in pins:
                        _PIN_CLAIMS.pop(p, None)

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
