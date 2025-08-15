"""
RoboHAT ↔ OLED command mirror test

Prereqs:
- RoboHAT connected at /dev/ttyACM1 (default)
- SSD1306 OLED 128x32 at I2C 0x3C (default)
- Run inside venv with requirements installed

Usage:
    source venv/bin/activate
    OLED_HEIGHT=32 timeout 25s python3 tests/hardware/robohat_oled_monitor_test.py

Expected:
- OLED displays lines like:
    SENT HH:MM:SS rc=enable
    OK   HH:MM:SS pwm,1500,1500
"""

import asyncio
import logging

from src.hardware.hardware_interface import create_hardware_interface


async def main():
    logging.basicConfig(level=logging.INFO)
    hw = create_hardware_interface()
    ok = await hw.initialize()
    if not ok:
        print("Hardware init failed")
        return 1

    # Send a few commands; they should appear on the OLED
    await asyncio.sleep(0.2)
    await hw.send_robohat_command('rc_enable')
    await asyncio.sleep(0.2)
    await hw.send_robohat_command('rc_mode', 'manual')
    await asyncio.sleep(0.2)
    await hw.send_robohat_command('pwm', 1500, 1500)
    await asyncio.sleep(0.2)
    await hw.send_robohat_command('blade_control', 'false')
    await asyncio.sleep(2.0)

    await hw.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
