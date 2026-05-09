"""
RP2040‑Zero RoboHAT controller – CircuitPython 9 / 10
Advanced RC Control System with configurable operation modes
  • RC PWM in  : GP6 (steer), GP5 (throttle), GP7 (aux1), GP4 (aux2), GP3 (aux3), GP2 (aux4)
  • Servo PWM out : GP10 (steer), GP11 (throttle)
  • Motor control: GP12 (blade)
  • Wheel encoder 1: GP8  (signal – Hall effect, KY-003; software polling, A-pin)
  • Wheel encoder 2: GP13 (signal – Hall effect, KY-003; software polling, B-pin conflicts with blade)
  • Status NeoPixel on GP16
  • Hardware UART  : GP0 (TX → Pi GPIO15/RX), GP1 (RX ← Pi GPIO14/TX) at 115200 baud

USB/UART commands (accepted on both interfaces simultaneously)
  rc=enable / rc=disable
  rc_mode=<mode>           – set RC control mode (emergency|manual|assisted|training)
  rc_config=<ch>,<func>    – configure channel function
  pwm,<steer>,<throttle>   (µs, 1000‑2000) when RC disabled
  blade=<on|off>           – blade control
  enc=zero                 – reset both wheel‑tick counters
  get_rc_status           – get comprehensive RC status
"""

from __future__ import annotations

import sys
import time
import os

import board
import busio
import digitalio
import pwmio
import supervisor
import microcontroller
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

# ---------- Hardware UART (GP0/GP1 = board.TX/RX) ---------- #
# Wiring: RP2040 GP0 (TX) → Pi GPIO15 (RXD / ttyAMA0 RX)
#         RP2040 GP1 (RX) ← Pi GPIO14 (TXD / ttyAMA0 TX)
# This gives a fully independent control path that works even when USB CDC
# fails (e.g. USB protocol error -71, bad cable, enumeration failure).
_hw_uart: busio.UART | None = None
_uart_rx_buf: str = ""
try:
    _hw_uart = busio.UART(board.TX, board.RX, baudrate=115200, timeout=0)
except Exception as _uart_err:  # noqa: BLE001
    print(f"Warning: hardware UART init failed: {_uart_err}")

# ---------- PWM servos ---------- #
PWM_FREQ = 50  # Hz

steer_pwm = pwmio.PWMOut(board.GP10, frequency=PWM_FREQ, duty_cycle=0)
thr_pwm   = pwmio.PWMOut(board.GP11, frequency=PWM_FREQ, duty_cycle=0)

# ---------- RC Control Modes ---------- #
class RCMode:
    EMERGENCY = "emergency"    # RC control only for emergency situations
    MANUAL = "manual"         # Complete manual control of all functions
    ASSISTED = "assisted"     # Manual control with safety oversight
    TRAINING = "training"     # Manual control with movement recording

# ---------- RC Channel Configuration ---------- #
RC_CHANNELS = {
    1: {"pin": board.GP6, "function": "steer", "min": 1000, "max": 2000, "center": 1500},
    2: {"pin": board.GP5, "function": "throttle", "min": 1000, "max": 2000, "center": 1500},
    3: {"pin": board.GP7, "function": "blade", "min": 1000, "max": 2000, "center": 1500},
    4: {"pin": board.GP4, "function": "speed_adj", "min": 1000, "max": 2000, "center": 1500},
    5: {"pin": board.GP3, "function": "emergency", "min": 1000, "max": 2000, "center": 1500},
    6: {"pin": board.GP2, "function": "mode_switch", "min": 1000, "max": 2000, "center": 1500},
}

# ---------- RC receiver (PulseIn) - Multi-channel ---------- #
rc_inputs = {}
for ch_num, config in RC_CHANNELS.items():
    try:
        rc_inputs[ch_num] = PulseIn(config["pin"], maxlen=100, idle_state=True)
        rc_inputs[ch_num].resume()
    except Exception as e:
        print(f"Warning: Failed to initialize RC channel {ch_num}: {e}")

# Additional motor control pins
blade_pwm = pwmio.PWMOut(board.GP12, frequency=PWM_FREQ, duty_cycle=0)

# ---------- Single-channel Hall effect wheel encoders ---------- #
# KY-003 / A3144 sensors wired to GP8 (enc1) and GP13 (enc2).
# countio.Counter can't be used:
#   GP8 = PWM4A (wrong channel type for countio)
#   GP13 = PWM6B, but blade_pwm uses PWM6A (same slice conflict)
# Both encoders use software edge detection in the main loop.
_enc1_pin = digitalio.DigitalInOut(board.GP8)
_enc1_pin.direction = digitalio.Direction.INPUT
_enc1_pin.pull = digitalio.Pull.UP
_enc1_prev = _enc1_pin.value
_enc1_count = 0
_enc2_pin = digitalio.DigitalInOut(board.GP13)
_enc2_pin.direction = digitalio.Direction.INPUT
_enc2_pin.pull = digitalio.Pull.UP
_enc2_prev = _enc2_pin.value
_enc2_count = 0

# ---------- Watchdog ---------- #
wdt = microcontroller.watchdog
wdt.timeout = 8
wdt.mode = WatchDogMode.RESET

# ---------- Globals ---------- #
rc_enabled        = True
rc_mode          = RCMode.EMERGENCY
last_serial_time  = time.monotonic()
SERIAL_TIMEOUT    = 5.0
_prev_led_state   = None
blade_enabled     = False
rc_signal_lost_time = None
SIGNAL_LOSS_TIMEOUT = 1.0
channel_data      = {}


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


def read_rc() -> dict[int, int]:
    """Read RC values from all configured channels"""
    global channel_data, rc_signal_lost_time
    
    current_data = {}
    signal_present = False
    
    for ch_num, rc_input in rc_inputs.items():
        if rc_input:
            pulses = [p for p in drain_pulsein(rc_input) if 800 <= p <= 2200][-5:]
            if pulses:
                current_data[ch_num] = sum(pulses) // len(pulses)
                signal_present = True
            else:
                # Use last known value or center position
                current_data[ch_num] = channel_data.get(ch_num, RC_CHANNELS[ch_num]["center"])
        else:
            current_data[ch_num] = RC_CHANNELS[ch_num]["center"]
    
    # Track signal loss
    if signal_present:
        rc_signal_lost_time = None
    elif rc_signal_lost_time is None:
        rc_signal_lost_time = time.monotonic()
    
    # Update global channel data
    channel_data.update(current_data)
    return current_data

def get_rc_channel_value(channel: int, function: str = None) -> int:
    """Get RC channel value by number or function"""
    if function:
        for ch_num, config in RC_CHANNELS.items():
            if config["function"] == function:
                return channel_data.get(ch_num, config["center"])
    return channel_data.get(channel, RC_CHANNELS.get(channel, {}).get("center", 1500))

def is_rc_signal_lost() -> bool:
    """Check if RC signal is lost"""
    return rc_signal_lost_time is not None and (time.monotonic() - rc_signal_lost_time) > SIGNAL_LOSS_TIMEOUT


def parse_cmd(line: str) -> tuple[str, str | None, str | None]:
    line = line.strip().lower()
    if line == "rc=enable":
        return "rc_enable", None, None
    if line == "rc=disable":
        return "rc_disable", None, None
    if line in ("enc=zero", "enc1=zero", "enc2=zero"):
        return "enc_zero", None, None
    if line == "get_rc_status":
        return "get_rc_status", None, None
    if line.startswith("rc_mode="):
        try:
            mode = line.split("=")[1]
            if mode in [RCMode.EMERGENCY, RCMode.MANUAL, RCMode.ASSISTED, RCMode.TRAINING]:
                return "rc_mode", mode, None
        except (IndexError, ValueError):
            pass
    if line.startswith("rc_config="):
        try:
            parts = line.split("=")[1].split(",")
            if len(parts) == 2:
                return "rc_config", parts[0], parts[1]
        except (IndexError, ValueError):
            pass
    if line.startswith("blade="):
        try:
            state = line.split("=")[1]
            if state in ["on", "off"]:
                return "blade", state, None
        except IndexError:
            pass
    if line.startswith("pwm,"):
        try:
            s, t = map(int, line.split(",")[1:3])
            if 1000 <= s <= 2000 and 1000 <= t <= 2000:
                return "pwm", str(s), str(t)
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


def read_uart_line() -> str | None:
    """Drain hardware UART bytes and return a complete line when one is ready."""
    global _uart_rx_buf  # pylint: disable=global-statement
    if _hw_uart is None or not _hw_uart.in_waiting:
        return None
    while _hw_uart.in_waiting:
        chunk = _hw_uart.read(_hw_uart.in_waiting)
        if not chunk:
            break
        _uart_rx_buf += chunk.decode("utf-8", errors="ignore")
    if "\n" in _uart_rx_buf or "\r" in _uart_rx_buf:
        for sep in ("\r\n", "\n", "\r"):
            if sep in _uart_rx_buf:
                line, _, _uart_rx_buf = _uart_rx_buf.partition(sep)
                return line.strip() if line.strip() else None
    return None


def uart_write(msg: str) -> None:
    """Send a response line back over hardware UART."""
    if _hw_uart is not None:
        try:
            _hw_uart.write((msg + "\r\n").encode("utf-8"))
        except Exception:  # noqa: BLE001
            pass


def get_circuitpython_version() -> str:
    """Return best-effort CircuitPython version across CP9/CP10 builds."""
    try:
        uname = os.uname()
        release = getattr(uname, "release", "")
        if release:
            return str(release)
    except Exception:
        pass

    try:
        impl = getattr(sys, "implementation", None)
        version = getattr(impl, "version", None)
        if version and len(version) >= 3:
            return f"{version[0]}.{version[1]}.{version[2]}"
    except Exception:
        pass

    return "unknown"


# ---------- main loop ---------- #
def main() -> None:
    global rc_enabled, last_serial_time, rc_mode, blade_enabled  # pylint: disable=global-statement
    global _enc1_count, _enc1_prev, _enc2_count, _enc2_prev

    set_pwm(1500, 1500)
    blade_pwm.duty_cycle = 0
    set_led(True, force=True)
    startup_msg = f"▶ RoboHAT Advanced RC Control ready (CircuitPython {get_circuitpython_version()})"
    print(startup_msg)
    uart_write(startup_msg)

    hb_t   = time.monotonic()
    channel_values = {}

    while True:
        wdt.feed()
        now = time.monotonic()

        # --- serial commands (USB CDC or hardware UART) --- #
        usb_line  = read_serial_line()
        uart_line = read_uart_line()

        for raw_line, source in ((usb_line, "USB"), (uart_line, "UART")):
            if not raw_line:
                continue
            tag = f"[{source}]"
            # Any received command resets the USB-timeout clock so that
            # status queries (get_rc_status, enc=zero, blade=…) do not
            # inadvertently drain the 2 s budget while RC is disabled.
            last_serial_time = now
            cmd, param1, param2 = parse_cmd(raw_line)

            def respond(msg: str) -> None:
                full = f"{tag} {msg}"
                print(full)
                uart_write(full)

            if cmd == "rc_enable":
                rc_enabled = True
                set_led(rc_enabled)
                respond(f"RC enabled, mode: {rc_mode}")
            elif cmd == "rc_disable":
                rc_enabled = False
                last_serial_time = now
                set_led(rc_enabled)
                respond("RC disabled – serial control")
            elif cmd == "rc_mode":
                rc_mode = param1
                respond(f"RC mode set to: {rc_mode}")
            elif cmd == "blade":
                blade_enabled = (param1 == "on")
                blade_pwm.duty_cycle = us_to_dc(2000) if blade_enabled else 0
                respond(f"Blade {'enabled' if blade_enabled else 'disabled'}")
            elif cmd == "get_rc_status":
                signal_lost = is_rc_signal_lost()
                status = {
                    "rc_enabled": rc_enabled,
                    "rc_mode": rc_mode,
                    "signal_lost": signal_lost,
                    "blade_enabled": blade_enabled,
                    "channels": channel_data,
                    "encoder_1": _enc1_count,
                    "encoder_2": _enc2_count,
                }
                respond(f"STATUS {status}")
            elif cmd == "enc_zero":
                _enc1_count = 0
                _enc1_prev = _enc1_pin.value
                _enc2_count = 0
                _enc2_prev = _enc2_pin.value
                respond("Encoder counters reset")
            elif cmd == "pwm" and not rc_enabled:
                set_pwm(int(param1), int(param2))
                last_serial_time = now
                respond(f"PWM set → steer={param1} µs throttle={param2} µs")
            else:
                respond(f"Invalid: {raw_line}")

        # --- serial timeout (no serial commands for SERIAL_TIMEOUT seconds) --- #
        if not rc_enabled and (now - last_serial_time) > SERIAL_TIMEOUT:
            rc_enabled = True
            set_led(rc_enabled)
            timeout_msg = f"[SERIAL] Timeout – back to RC mode: {rc_mode}"
            print(timeout_msg)
            uart_write(timeout_msg)

        # --- control path --- #
        if rc_enabled:
            channel_values = read_rc()
            
            # Handle signal loss
            if is_rc_signal_lost():
                # Emergency failsafe - center all controls
                set_pwm(1500, 1500)
                blade_pwm.duty_cycle = 0
                blade_enabled = False
                pixel[0] = (255, 255, 0)  # Yellow for signal loss
                pixel.show()
            else:
                # Normal RC control based on mode
                steer_val = channel_values.get(1, 1500)
                throttle_val = channel_values.get(2, 1500)
                
                # Emergency stop check (channel 5)
                emergency_val = channel_values.get(5, 1500)
                if emergency_val < 1200:  # Emergency stop triggered
                    set_pwm(1500, 1500)
                    blade_pwm.duty_cycle = 0
                    blade_enabled = False
                    pixel[0] = (255, 0, 0)  # Red for emergency stop
                    pixel.show()
                else:
                    # Normal operation
                    set_pwm(steer_val, throttle_val)
                    
                    # Blade control (channel 3)
                    blade_val = channel_values.get(3, 1500)
                    if rc_mode in [RCMode.MANUAL, RCMode.ASSISTED] and blade_val > 1700:
                        blade_enabled = True
                        blade_pwm.duty_cycle = us_to_dc(2000)
                    else:
                        blade_enabled = False
                        blade_pwm.duty_cycle = 0
                    
                    set_led(rc_enabled)

        # --- heartbeat --- #
        if now - hb_t >= 5:
            control_source = f"RC-{rc_mode}" if rc_enabled else "SERIAL"
            signal_status = "LOST" if is_rc_signal_lost() else "OK"
            hb_msg = (
                f"[{control_source}] signal={signal_status} "
                f"steer={channel_values.get(1, 1500)} µs "
                f"thr={channel_values.get(2, 1500)} µs "
                f"blade={'ON' if blade_enabled else 'OFF'} "
                f"enc_1={_enc1_count} enc_2={_enc2_count}"
            )
            print(hb_msg)
            uart_write(hb_msg)
            hb_t = now

        # Software edge-count for both encoders (GP8/GP13; countio not usable, see init)
        _enc1_now = _enc1_pin.value
        if _enc1_now != _enc1_prev:  # any transition = magnet edge
            _enc1_count += 1
        _enc1_prev = _enc1_now
        _enc2_now = _enc2_pin.value
        if _enc2_now != _enc2_prev:  # any transition = magnet edge
            _enc2_count += 1
        _enc2_prev = _enc2_now
        time.sleep(0.002)


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001
        print(f"[FATAL] {err!r}")
    finally:
        set_pwm(1500, 1500)
        pixel[0] = (255, 0, 0)  # red = halted/error
        pixel.show()
