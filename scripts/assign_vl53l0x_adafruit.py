#!/usr/bin/env python3
"""
Adafruit-style VL53L0X dual-sensor address assignment for Raspberry Pi (Bookworm).

Sequence (based on Adafruit example):
1) Hold both sensors in reset (XSHUT LOW)
2) Enable the sensor that should become 0x30, initialize at default 0x29, set address to 0x30
3) Enable the remaining sensor; it will stay at default 0x29
4) Verify both 0x29 and 0x30 are present; persist data/tof_no_gpio.json

Run inside repo venv:
  timeout 90s venv/bin/python scripts/assign_vl53l0x_adafruit.py

Notes:
- Reads XSHUT GPIO pins from config/hardware.yaml (fallback to BCM 22/23)
- Uses Blinka (board/busio/digitalio) + Adafruit VL53L0X driver
- Uses small sleeps to allow boot/address operations to settle
"""
import time
import json
import sys
from pathlib import Path

# Ensure repo src is on path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Lazy import yaml; fallback to defaults if unavailable
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # type: ignore

# Blinka / Adafruit
try:
    import board  # type: ignore
    import busio  # type: ignore
    from digitalio import DigitalInOut, Direction  # type: ignore
    from adafruit_vl53l0x import VL53L0X  # type: ignore
except Exception as e:
    print(f"ERROR: Required hardware libraries not available: {e}", file=sys.stderr)
    sys.exit(2)

# Defaults if config not present
DEFAULT_LEFT_XSHUT_BCM = 22
DEFAULT_RIGHT_XSHUT_BCM = 23

CONFIG_PATH = REPO_ROOT / 'config' / 'hardware.yaml'
STATE_PATH = REPO_ROOT / 'data' / 'tof_no_gpio.json'


def load_xshut_pins():
    left = DEFAULT_LEFT_XSHUT_BCM
    right = DEFAULT_RIGHT_XSHUT_BCM
    try:
        if yaml and CONFIG_PATH.exists():
            data = yaml.safe_load(CONFIG_PATH.read_text())
            # Accept both nested paths and top-level overrides
            # Look for keys tof_left_shutdown / tof_right_shutdown
            if isinstance(data, dict):
                # Direct keys
                left = int(data.get('tof_left_shutdown', left))
                right = int(data.get('tof_right_shutdown', right))
                # Or nested under gpio / pins
                gpio = data.get('gpio') if isinstance(data.get('gpio'), dict) else None
                if gpio:
                    pins = gpio.get('pins') if isinstance(gpio.get('pins'), dict) else None
                    if pins:
                        left = int(pins.get('tof_left_shutdown', left))
                        right = int(pins.get('tof_right_shutdown', right))
    except Exception:
        pass
    return left, right


def bcm_to_board_pin(bcm_num: int):
    """Map BCM N to board.DN attribute for Blinka digitalio."""
    attr = f'D{bcm_num}'
    if hasattr(board, attr):
        return getattr(board, attr)
    raise RuntimeError(f"Board pin for BCM{bcm_num} not found (expected board.{attr})")


def persist_no_gpio_flag():
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'no_gpio_always': True,
            'confirmed_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'note': 'ToF addresses 0x29 and 0x30 confirmed by adafruit-style assigner.'
        }
        STATE_PATH.write_text(json.dumps(payload, indent=2))
        print(f"Persisted flag: {STATE_PATH}")
    except Exception as e:
        print(f"WARN: could not persist no-GPIO flag: {e}", file=sys.stderr)


def main() -> int:
    left_bcm, right_bcm = load_xshut_pins()
    print(f"Using XSHUT pins BCM left={left_bcm}, right={right_bcm}")

    # Setup I2C
    i2c = busio.I2C(board.SCL, board.SDA)

    # Setup XSHUT lines
    left_pin = DigitalInOut(bcm_to_board_pin(left_bcm))
    left_pin.direction = Direction.OUTPUT
    right_pin = DigitalInOut(bcm_to_board_pin(right_bcm))
    right_pin.direction = Direction.OUTPUT

    try:
        # 1) Hold both low (sensors OFF)
        left_pin.value = False
        right_pin.value = False
        time.sleep(0.05)

        # 2) Bring up RIGHT first -> will become 0x30
        right_pin.value = True
        time.sleep(0.1)
        s_right = VL53L0X(i2c)  # at default 0x29
        time.sleep(0.05)
        s_right.set_address(0x30)
        time.sleep(0.05)
        print("Right sensor set to 0x30")

        # 3) Bring up LEFT -> remains 0x29
        left_pin.value = True
        time.sleep(0.1)
        s_left = VL53L0X(i2c)  # at default 0x29
        time.sleep(0.05)

        # Optional: start continuous to warm them
        try:
            s_right.start_continuous()
            s_left.start_continuous()
        except Exception:
            pass

        # Verify with a bus scan
        addrs = []
        if i2c.try_lock():
            try:
                addrs = i2c.scan()
            finally:
                i2c.unlock()
        print("I2C devices now:", [hex(a) for a in addrs])
        if 0x29 in addrs and 0x30 in addrs:
            persist_no_gpio_flag()
            print("SUCCESS: ToF sensors confirmed at 0x29 and 0x30.")
            return 0
        print("ERROR: Expected both 0x29 and 0x30, but scan shows:", [hex(a) for a in addrs], file=sys.stderr)
        return 1
    finally:
        # Best-effort cleanup: leave both sensors ENABLED (XSHUT HIGH) so that
        # subsequent no-GPIO runs can detect sensors at 0x29/0x30 without having
        # to toggle GPIO again.
        try:
            left_pin.value = True
            right_pin.value = True
        except Exception:
            pass
        try:
            left_pin.deinit()
            right_pin.deinit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
