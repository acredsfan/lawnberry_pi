# Minimal dual VL53L0X read test without XSHUT toggling
# Assumes right sensor is at 0x30 and left at 0x29 (use scripts/fix_tof_sensors.py first)

import time
import sys

import board
from adafruit_vl53l0x import VL53L0X


def main(count: int = 5) -> int:
    i2c = board.I2C()

    # Optional: show devices on the bus
    if i2c.try_lock():
        try:
            addrs = i2c.scan()
            print("I2C scan:", [hex(a) for a in addrs])
        finally:
            i2c.unlock()

    sensors = []

    # Try to open right (0x30)
    try:
        right = VL53L0X(i2c, address=0x30)
        sensors.append(("right(0x30)", right))
        print("Opened right sensor at 0x30")
    except Exception as e:
        print("Right sensor open failed:", e)

    # Try to open left (0x29)
    try:
        left = VL53L0X(i2c, address=0x29)
        sensors.append(("left(0x29)", left))
        print("Opened left sensor at 0x29")
    except Exception as e:
        print("Left sensor open failed:", e)

    if not sensors:
        print("No VL53L0X sensors opened. Run scripts/fix_tof_sensors.py and check wiring.")
        return 1

    # Read a few ranges
    for _ in range(max(1, count)):
        for name, s in sensors:
            try:
                print(f"{name} range: {s.range} mm")
            except Exception as e:
                print(f"{name} read failed: {e}")
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
