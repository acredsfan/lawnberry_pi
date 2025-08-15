"""
OLED Display Test (I2C @ 0x3C)
- Supports SSD1306 and SH1106 (via env var)
- Renders a few lines of text and a simple box

Run inside venv:
    source venv/bin/activate
    # Default: SSD1306 128x64
    timeout 20s python3 tests/hardware/display_test.py

    # If your module is 128x32 (common), set height:
    OLED_HEIGHT=32 timeout 20s python3 tests/hardware/display_test.py

    # If your module uses SH1106 driver:
    OLED_DRIVER=sh1106 timeout 20s python3 tests/hardware/display_test.py
"""

import time
import os

import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

try:
        import adafruit_sh110x  # optional, only needed if OLED_DRIVER=sh1106
except Exception:  # pragma: no cover
        adafruit_sh110x = None


def main() -> int:
    # I2C bus
    i2c = board.I2C()  # SCL/SDA from Pi header

    # Config via env
    width = int(os.getenv("OLED_WIDTH", "128"))
    height = int(os.getenv("OLED_HEIGHT", "64"))
    driver = os.getenv("OLED_DRIVER", "ssd1306").lower()  # ssd1306 | sh1106
    addr = int(os.getenv("OLED_ADDR", "0x3C"), 16)
    reset_pin = None  # use internal reset if not wired; for external reset, pass a DigitalInOut

    # Initialize display
    if driver == "sh1106":
        if adafruit_sh110x is None:
            raise RuntimeError("OLED_DRIVER=sh1106 set but adafruit_sh110x not available")
        disp = adafruit_sh110x.SH1106_I2C(width, height, i2c, address=addr, reset=reset_pin)
    else:
        disp = adafruit_ssd1306.SSD1306_I2C(width, height, i2c, addr=addr, reset=reset_pin)
    disp.fill(0)
    disp.show()

    # Create image buffer
    image = Image.new("1", (width, height))
    draw = ImageDraw.Draw(image)

    # Border box
    draw.rectangle((0, 0, width - 1, height - 1), outline=255, fill=0)

    # Text
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Slightly increased line spacing avoids cropping on some panels
    y = 2
    def line(text: str):
        nonlocal y
        draw.text((4, y), text, font=font, fill=255)
        y += 12 if height >= 64 else 10

    line("LawnBerryPi")
    line("Display Online")
    line("I2C: 0x3C SSD1306")
    line(time.strftime("%H:%M:%S"))

    # Simple progress bar demo
    bar_top = height - (14 if height >= 48 else 10)
    bar_bot = height - (6 if height >= 48 else 4)
    draw.rectangle((4, bar_top, width - 4, bar_bot), outline=255, fill=0)
    for pct in (20, 40, 60, 80, 100):
        fill_w = int((width - 8) * pct / 100)
        draw.rectangle((5, bar_top + 1, 5 + fill_w, bar_bot - 1), outline=255, fill=255)
        disp.image(image)
        disp.show()
        time.sleep(0.3)
        # clear bar area for next step
        draw.rectangle((5, bar_top + 1, width - 5, bar_bot - 1), outline=0, fill=0)
        # redraw static elements
        draw.rectangle((0, 0, width - 1, height - 1), outline=255, fill=0)
        y = 2
        line("LawnBerryPi")
        line("Display Online")
        line("I2C: 0x3C SSD1306")
        line(time.strftime("%H:%M:%S"))
        draw.rectangle((4, bar_top, width - 4, bar_bot), outline=255, fill=0)

    # Final frame
    draw.text((4, height - 12), "Done", font=font, fill=255)
    disp.image(image)
    disp.show()
    time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
