"""
RP2040‑Zero RoboHAT controller – CircuitPython 9 / 10
  • RC PWM in  : GP6 (steer), GP5 (throttle)
  • Servo PWM out : GP10 (steer), GP11 (throttle)
  • Wheel encoder : GP8 (A), GP9 (B)
  • Status NeoPixel on GP16
USB commands
  rc=enable / rc=disable
  pwm,<steer>,<throttle>   (µs, 1000‑2000) when RC disabled
  enc=zero                 – reset wheel‑tick counter
"""

from __future__ import annotations

import sys
import time

import board
import digitalio
import pwmio
import supervisor
import microcontroller
import rotaryio
import adafruit_pixelbuf
import neopixel_write
from pulseio import PulseIn

# ----- Watchdog enum location changed in CP 9 ----- #
try:
    from watchdog import WatchDogMode  # CP ≥ 9
except ImportError:                    # CP ≤ 8
    from microcontroller import WatchDogMode  # type: ignore

# ---------- NeoPixel helper ---------- #
class SimpleNeoPixel(adafruit_pixelbuf.PixelBuf):
    def __init__(self, pin, n, *, brightness=1.0, auto_write=True, byteorder="GRB"):
        self._pin = digitalio.DigitalInOut(pin)
        self._pin.direction = digitalio.Direction.OUTPUT
        super().__init__(n, brightness=brightness, byteorder=byteorder, auto_write=auto_write)

    # new requirement in adafruit_pixelbuf 9+
    def _transmit(self, buf: memoryview) -> None:  # pylint: disable=invalid-name
        neopixel_write.neopixel_write(self._pin, buf)


pixel = SimpleNeoPixel(board.GP16, 1, brightness=0.3)

# ---------- PWM servos ---------- #
PWM_FREQ = 50  # Hz

steer_pwm = pwmio.PWMOut(board.GP10, frequency=PWM_FREQ, duty_cycle=0)
thr_pwm   = pwmio.PWMOut(board.GP11, frequency=PWM_FREQ, duty_cycle=0)

# ---------- RC receiver (PulseIn) ---------- #
steer_rc = PulseIn(board.GP6, maxlen=100, idle_state=True)
thr_rc   = PulseIn(board.GP5, maxlen=100, idle_state=True)
steer_rc.resume()
thr_rc.resume()

# ---------- Quadrature encoder ---------- #
encoder = rotaryio.IncrementalEncoder(board.GP8, board.GP9)
encoder.position = 0

# ---------- Watchdog ---------- #
wdt = microcontroller.watchdog
wdt.timeout = 8
wdt.mode = WatchDogMode.RESET

# ---------- Globals ---------- #
rc_enabled        = True
last_serial_time  = time.monotonic()
SERIAL_TIMEOUT    = 2.0
_prev_led_state   = None


# ---------- helpers ---------- #
def us_to_dc(us: int, freq: int = PWM_FREQ) -> int:
    period_us = 1_000_000 / freq
    return max(0, min(65535, int(us / period_us * 65535)))


def set_pwm(steer_us: int, thr_us: int) -> None:
    steer_pwm.duty_cycle = us_to_dc(steer_us)
    thr_pwm.duty_cycle   = us_to_dc(thr_us)


def drain_pulsein(pin: PulseIn) -> list[int]:
    """Return all pulses then clear the buffer. Works in CP 9 & 10."""
    pulses: list[int] = []
    # CP ≤9 supported iteration; CP 10 does not
    try:
        pulses = list(pin)
        pin.clear()
    except TypeError:
        while len(pin):
            pulses.append(pin.popleft())
    return pulses


def read_rc() -> tuple[int, int]:
    steer = [p for p in drain_pulsein(steer_rc) if 800 <= p <= 2200][-5:]
    thr   = [p for p in drain_pulsein(thr_rc)   if 800 <= p <= 2200][-5:]
    return (
        sum(steer) // len(steer) if steer else 1500,
        sum(thr)   // len(thr)   if thr   else 1500,
    )


def parse_cmd(line: str) -> tuple[str, int | None, int | None]:
    line = line.strip().lower()
    if line == "rc=enable":
        return "rc_enable", None, None
    if line == "rc=disable":
        return "rc_disable", None, None
    if line == "enc=zero":
        return "enc_zero", None, None
    if line.startswith("pwm,"):
        try:
            s, t = map(int, line.split(",")[1:3])
            if 1000 <= s <= 2000 and 1000 <= t <= 2000:
                return "pwm", s, t
        except (ValueError, IndexError):
            pass
    return "invalid", None, None


def set_led(rc: bool, *, force=False) -> None:
    global _prev_led_state  # pylint: disable=global-statement
    if force or rc != _prev_led_state:
        pixel[0] = (0, 255, 0) if rc else (0, 0, 255)
        pixel.show()
        _prev_led_state = rc


def read_serial_line() -> str | None:
    buf = ""
    while supervisor.runtime.serial_bytes_available:
        ch = sys.stdin.read(1)
        if ch in ("\n", "\r"):
            return buf if buf else None
        buf += ch
    return None


# ---------- main loop ---------- #
def main() -> None:
    global rc_enabled, last_serial_time  # pylint: disable=global-statement

    set_pwm(1500, 1500)
    set_led(True, force=True)
    print("▶ RoboHAT ready (CircuitPython ", microcontroller.circuitpython_version, ")")

    hb_t   = time.monotonic()
    steer  = thr = 1500

    while True:
        wdt.feed()
        now = time.monotonic()

        # --- USB commands --- #
        if (line := read_serial_line()):
            cmd, s_val, t_val = parse_cmd(line)
            if cmd == "rc_enable":
                rc_enabled = True
                set_led(rc_enabled)
                print("[USB] RC enabled")
            elif cmd == "rc_disable":
                rc_enabled = False
                last_serial_time = now
                set_led(rc_enabled)
                print("[USB] RC disabled – USB control")
            elif cmd == "enc_zero":
                encoder.position = 0
                print("[USB] Encoder counter reset")
            elif cmd == "pwm" and not rc_enabled:
                set_pwm(s_val, t_val)
                last_serial_time = now
                print(f"[USB] PWM set → steer={s_val} µs throttle={t_val} µs")
            else:
                print(f"[USB] Invalid: {line}")

        # --- USB timeout --- #
        if not rc_enabled and (now - last_serial_time) > SERIAL_TIMEOUT:
            rc_enabled = True
            set_led(rc_enabled)
            print("[USB] Timeout – back to RC")

        # --- control path --- #
        if rc_enabled:
            steer, thr = read_rc()
            set_pwm(steer, thr)

        # --- heartbeat --- #
        if now - hb_t >= 5:
            mode = "RC" if rc_enabled else "USB"
            print(
                f"[{mode}] steer={steer} µs "
                f"thr={thr} µs "
                f"enc={encoder.position}"
            )
            hb_t = now

        time.sleep(0.02)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001
        print(f"[FATAL] {err!r}")
    finally:
        set_pwm(1500, 1500)
        pixel[0] = (255, 0, 0)  # red = halted/error
        pixel.show()
