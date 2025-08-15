# Diagnose VL53L0X XSHUT wiring and address behavior
# Uses Blinka's DigitalInOut on board.D22 (left) and board.D23 (right)

import time
import board
from digitalio import DigitalInOut, Direction


def scan(i2c):
    addrs = []
    if i2c.try_lock():
        try:
            addrs = i2c.scan()
        finally:
            i2c.unlock()
    print("I2C scan:", [hex(a) for a in addrs])
    return addrs


i2c = board.I2C()

left = DigitalInOut(board.D22)
left.direction = Direction.OUTPUT
right = DigitalInOut(board.D23)
right.direction = Direction.OUTPUT

# XSHUT is active-low: low=off, high=on

print("Both OFF (low)")
left.value = False
right.value = False
time.sleep(0.2)
scan(i2c)

print("RIGHT ON only (0x29 expected if working)")
right.value = True
time.sleep(0.3)
scan(i2c)

print("LEFT ON too (0x29 + whatever right was changed to)")
left.value = True
time.sleep(0.3)
scan(i2c)

print("Now RIGHT OFF (leave only LEFT on)")
right.value = False
time.sleep(0.3)
scan(i2c)

print("Cleanup: both OFF")
left.value = False
right.value = False
