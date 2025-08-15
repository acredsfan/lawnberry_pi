# SPDX-FileCopyrightText: 2021 Smankusors for Adafruit Industries
# SPDX-License-Identifier: MIT

"""
Example of how to use the adafruit_vl53l0x library to change the assigned address of
multiple VL53L0X sensors on the same I2C bus. This example only focuses on 2 VL53L0X
sensors, but can be modified for more. BE AWARE: a multitude of sensors may require
more current than the on-board 3V regulator can output (typical current consumption during
active range readings is about 19 mA per sensor).

This example like vl53l0x_multiple_sensors, but this with sensors in continuous mode.
So you don't need to wait the sensor to do range measurement and return the distance
for you.

For example, you have 2 VL53L0X sensors, with timing budget of 200ms, on single mode.
When you want to get distance from sensor #1, sensor #2 will idle because waiting
for sensor #1 completes the range measurement. You could do multithreading so you
can ask both the sensor at the same time, but it's quite expensive.

When you use continuous mode, the sensor will always do range measurement after it
completes. So when you want to get the distance from both of the device, you don't
need to wait 400ms, just 200ms for both of the sensors.
"""

import time

import board
from digitalio import DigitalInOut

from adafruit_vl53l0x import VL53L0X

# declare the singleton variable for the default I2C bus
i2c = board.I2C()  # uses board.SCL and board.SDA
# i2c = board.STEMMA_I2C()  # For using the built-in STEMMA QT connector on a microcontroller

# declare the digital output pins connected to the "SHDN" pin on each VL53L0X sensor
# NOTE: LawnBerryPi wiring uses GPIO 22 (left XSHUT) and GPIO 23 (right XSHUT)
# Adjust these to match your hardware if different.
xshut = [
    DigitalInOut(board.D22),  # Left sensor XSHUT
    DigitalInOut(board.D23),  # Right sensor XSHUT
]

for power_pin in xshut:
    # make sure these pins are a digital output, not a digital input
    power_pin.switch_to_output(value=False)
    # These pins are active when Low, meaning:
    #   if the output signal is LOW, then the VL53L0X sensor is off.
    #   if the output signal is HIGH, then the VL53L0X sensor is on.
# all VL53L0X sensors are now off

# initialize a list to be used for the array of VL53L0X sensors
vl53 = []

def scan_once():
    addrs = []
    if i2c.try_lock():
        try:
            addrs = i2c.scan()
        finally:
            i2c.unlock()
    return addrs

# Bring up RIGHT sensor first and ensure it ends up at 0x30
xshut[1].value = True
time.sleep(1.0)  # allow boot
addrs = scan_once()
if 0x29 in addrs:
    try:
        right = VL53L0X(i2c, address=0x29)
    except Exception:
        time.sleep(0.5)
        right = VL53L0X(i2c, address=0x29)
    right.start_continuous()
    right.set_address(0x30)
    vl53.append(right)
elif 0x30 in addrs:
    right = VL53L0X(i2c, address=0x30)
    right.start_continuous()
    vl53.append(right)
else:
    raise RuntimeError("Right VL53L0X not found at 0x29 or 0x30 after enabling XSHUT")

# Bring up LEFT sensor (should be at 0x29)
xshut[0].value = True
time.sleep(1.0)
addrs = scan_once()
if 0x29 in addrs:
    try:
        left = VL53L0X(i2c, address=0x29)
    except Exception:
        time.sleep(0.5)
        left = VL53L0X(i2c, address=0x29)
    left.start_continuous()
    vl53.append(left)
else:
    raise RuntimeError("Left VL53L0X not found at 0x29 after enabling XSHUT")
# there is a helpful list of pre-designated I2C addresses for various I2C devices at
# https://learn.adafruit.com/i2c-addresses/the-list
# According to this list 0x30-0x34 are available, although the list may be incomplete.
# In the python REPR, you can scan for all I2C devices that are attached and detirmine
# their addresses using:
#   >>> import board
#   >>> i2c = board.I2C()  # uses board.SCL and board.SDA
#   >>> if i2c.try_lock():
#   >>>     [hex(x) for x in i2c.scan()]
#   >>>     i2c.unlock()


def detect_range(count=5):
    """take count=5 samples"""
    while count:
        for index, sensor in enumerate(vl53):
            print(f"Sensor {index + 1} Range: {sensor.range}mm")
        time.sleep(1.0)
        count -= 1


def stop_continuous():
    """this is not required, if you use XSHUT to reset the sensor.
    unless if you want to save some energy
    """
    for sensor in vl53:
        sensor.stop_continuous()


if __name__ == "__main__":
    detect_range()
    stop_continuous()
else:
    print(
        "Multiple VL53L0X sensors' addresses are assigned properly\n"
        "execute detect_range() to read each sensors range readings.\n"
        "When you are done with readings, execute stop_continuous()\n"
        "to stop the continuous mode."
    )