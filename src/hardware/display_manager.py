"""OLED Display Manager for mirroring RoboHAT commands on SSD1306 (0x3C).

Design goals:
- Optional: if hardware or libraries are missing, it silently disables itself
- Non-blocking: lightweight async API with internal lock to serialize draws
- 128x32 by default (SSD1306 @ 0x3C), env-overridable for height/address

Bookworm/RPi notes:
- Uses Adafruit Blinka (board + busio) and adafruit-circuitpython-ssd1306
- Pillow is used to render text to an image buffer
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from typing import Deque, List, Optional


class OLEDDisplayManager:
    """Manages a small OLED (SSD1306/SH1106) for status/command mirroring.

    Public contract:
    - await initialize(): Try to set up display (optional). Returns bool enabled.
    - async log_line(text): Append a line and redraw (bounded history by height)
    - async show_lines(lines): Replace lines and redraw
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
    self.enabled: bool = False
        self._disp = None  # type: ignore
        self._width: int = int(os.getenv("OLED_WIDTH", "128"))
        self._height: int = int(os.getenv("OLED_HEIGHT", "32"))
        self._addr: int = int(os.getenv("OLED_ADDR", "0x3C"), 16)
        self._driver: str = os.getenv("OLED_DRIVER", "ssd1306").lower()
        self._lock = asyncio.Lock()
        self._history: Deque[str] = deque(maxlen=4 if self._height <= 32 else 6)
        self._imports_ok: bool = False
    self._disabled_flag: bool = os.getenv("OLED_DISABLE", "0").lower() in {"1", "true", "yes"}

    # File logging (works even if display disabled)
    self._log_path: str = os.getenv("OLED_LOG_PATH", "data/robohat_commands.log")
    self._max_log_lines: int = int(os.getenv("OLED_LOG_MAX_LINES", "200"))
    self._since_trim: int = 0

        # Pillow drawing state
        self._Image = None
        self._ImageDraw = None
        self._ImageFont = None

    async def initialize(self) -> bool:
        """Initialize the OLED; returns True if ready, else False.

        Never raises if display missing; just logs and disables itself.
        """
        # Respect runtime disable flag
        if self._disabled_flag:
            self.enabled = False
            self.logger.info("OLED display disabled by OLED_DISABLE env var")
            return False

        # Import here to avoid mandatory dependency when unused
        try:
            import board  # type: ignore
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
            import adafruit_ssd1306  # type: ignore
            try:
                import adafruit_sh110x  # type: ignore
            except Exception:
                adafruit_sh110x = None  # type: ignore

            # Cache Pillow symbols
            self._Image, self._ImageDraw, self._ImageFont = Image, ImageDraw, ImageFont
            self._imports_ok = True

            # Set up I2C and display
            i2c = board.I2C()  # Uses default SCL/SDA pins
            if self._driver == "sh1106":
                if adafruit_sh110x is None:
                    raise RuntimeError("OLED_DRIVER=sh1106 but adafruit_sh110x not installed")
                self._disp = adafruit_sh110x.SH1106_I2C(
                    self._width, self._height, i2c, address=self._addr, reset=None
                )
            else:
                self._disp = adafruit_ssd1306.SSD1306_I2C(
                    self._width, self._height, i2c, addr=self._addr, reset=None
                )

            # Clear screen
            self._disp.fill(0)
            self._disp.show()

            self.enabled = True
            self.logger.info(
                f"OLED display initialized at 0x{self._addr:02x} ({self._width}x{self._height}, {self._driver})"
            )
            # Initial banner
            await self.show_lines([
                "LawnBerryPi",
                "RoboHAT Cmds:",
                time.strftime("%H:%M:%S"),
            ])
            return True

        except Exception as e:
            # Graceful fallback
            self.enabled = False
            self._disp = None
            self.logger.warning(f"OLED display not available: {e}")
            return False

    async def log_line(self, text: str) -> None:
        """Append a line and redraw the display (if enabled)."""
        if not self.enabled:
            return
        # Truncate to fit display width (approximate: 21 chars for 128x32 default font)
        max_chars = 21 if self._height <= 32 else 21  # default font is fixed width; safe cap
        self._history.append(text[:max_chars])
        await self._redraw()

    async def show_lines(self, lines: List[str]) -> None:
        """Replace lines and redraw the display (if enabled)."""
        if not self.enabled:
            return
        max_len = self._history.maxlen or 4
        pruned = [ln[:21] for ln in lines[:max_len]]
        self._history.clear()
        self._history.extend(pruned)
        await self._redraw()

    async def log_robohat_command(self, command: str, success: Optional[bool] = None) -> None:
        """Convenience: format and log a RoboHAT command line."""
        status = "OK" if success else ("ERR" if success is False else "SENT")
        ts = time.strftime("%H:%M:%S")
        line = f"{status} {ts} {command}"
        # Always write to file (rolling log)
        await self._log_to_file(line)
        # Render on display if enabled
        if self.enabled:
            await self.log_line(line)

    async def _redraw(self) -> None:
        if not self.enabled or not self._imports_ok or self._disp is None:
            return
        async with self._lock:
            try:
                # Create buffer image
                image = self._Image.new("1", (self._width, self._height))
                draw = self._ImageDraw.Draw(image)

                # Optional border for clarity
                draw.rectangle((0, 0, self._width - 1, self._height - 1), outline=255, fill=0)

                # Choose font
                try:
                    font = self._ImageFont.load_default()
                except Exception:
                    font = None

                # Render lines
                y = 2
                line_step = 10 if self._height <= 32 else 12
                for ln in list(self._history):
                    draw.text((3, y), ln, font=font, fill=255)
                    y += line_step

                # Push to display
                self._disp.image(image)
                self._disp.show()
            except Exception as e:
                self.logger.debug(f"OLED redraw failed: {e}")

    async def _log_to_file(self, line: str) -> None:
        """Append to a local log file and keep it trimmed to last N lines."""
        try:
            # Ensure directory exists
            import os
            from pathlib import Path

            log_path = Path(self._log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Append line
            with log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

            # Trim occasionally to keep file small
            self._since_trim += 1
            if self._since_trim >= 20:
                self._since_trim = 0
                # Read and keep last _max_log_lines
                try:
                    with log_path.open("r", encoding="utf-8") as f:
                        lines = f.readlines()
                    if len(lines) > self._max_log_lines:
                        tail = lines[-self._max_log_lines :]
                        with log_path.open("w", encoding="utf-8") as f:
                            f.writelines(tail)
                except Exception as e:
                    self.logger.debug(f"OLED log trim skipped: {e}")
        except Exception as e:
            self.logger.debug(f"OLED file log failed: {e}")
