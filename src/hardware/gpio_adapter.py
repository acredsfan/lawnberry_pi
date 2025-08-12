"""GPIO abstraction layer for Raspberry Pi 4B and 5."""

try:
    import RPi.GPIO as _GPIO  # Legacy library on Pi 4B

    GPIO = _GPIO
except Exception:
    try:
        import lgpio
    except Exception:  # pragma: no cover
        lgpio = None

    class _LGPIOAdapter:
        BCM = "BCM"
        OUT = lgpio.OUTPUT if lgpio else 0
        IN = lgpio.INPUT if lgpio else 1
        PUD_UP = lgpio.PULL_UP if lgpio else 1
        PUD_DOWN = lgpio.PULL_DOWN if lgpio else 2
        PUD_OFF = lgpio.PULL_NONE if lgpio else 0

        def __init__(self):
            self._chip = None

        def setmode(self, mode):  # noqa: D401
            """Ignore mode; kept for compatibility."""
            if lgpio and self._chip is None:
                self._chip = lgpio.gpiochip_open(0)

        def setwarnings(self, flag):
            return None

        def setup(self, pin, direction, pull_up_down=PUD_OFF, initial=0):
            if lgpio is None:
                return
            if self._chip is None:
                self.setmode(self.BCM)
            if direction == self.OUT:
                lgpio.gpio_claim_output(self._chip, pin, initial)
            else:
                lgpio.gpio_claim_input(self._chip, pin, pull_up_down)

        def output(self, pin, value):
            if lgpio and self._chip is not None:
                lgpio.gpio_write(self._chip, pin, value)

        def input(self, pin):
            if lgpio and self._chip is not None:
                return lgpio.gpio_read(self._chip, pin)
            return 0

        def cleanup(self):
            if lgpio and self._chip is not None:
                lgpio.gpiochip_close(self._chip)
                self._chip = None

    GPIO = _LGPIOAdapter()

__all__ = ["GPIO"]
