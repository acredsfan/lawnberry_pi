"""BNO085 IMU driver (T046).

Reads from a BNO085 in UART/RVC (Robot Vacuum Cleaner) mode via pyserial.

## RVC packet format (21 bytes total)
  Byte  0-1 : header 0xAA 0xAA
  Byte    2 : sequence index (0-255, wraps)
  Byte  3-4 : yaw   (int16 LE, units = 0.01 deg, range 0-360 deg)
  Byte  5-6 : pitch (int16 LE, units = 0.01 deg)
  Byte  7-8 : roll  (int16 LE, units = 0.01 deg)
  Byte 9-10 : x accel (int16 LE, units = 0.01 m/s^2)
  Byte 11-12: y accel
  Byte 13-14: z accel
  Byte 15-19: reserved (5 bytes)
  Byte   20 : checksum = (sum of bytes 2-19) & 0xFF

## Calibration status in RVC mode
The BNO085 RVC protocol does NOT transmit calibration registers.
Calibration happens internally; the chip self-calibrates its gyro,
accelerometer and magnetometer but does not surface the per-sensor
confidence levels (0-3) in the RVC packet.

  - Before the first valid frame is received: "uncalibrated"
  - After the first valid frame (sensor is producing output):
    "rvc_active" -- the sensor is running and applying its internally
    managed calibration; the numeric level is simply not available via
    this protocol.

To obtain numeric calibration levels (0-3 per subsystem) the BNO085 must
be accessed via the full SHTP protocol (I2C or SPI) using a library such
as adafruit-circuitpython-bno08x.  That interface is not wired up in
this driver; "rvc_active" is the best available status.

Safety Requirement (FR-022): Tilt >30 degrees must trigger blade stop
within 200ms.  Enforcement occurs in safety triggers (T051); this driver
only supplies data.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import random
import struct
import time
from dataclasses import dataclass
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver

logger = logging.getLogger(__name__)

# RVC frame constants
_RVC_HEADER_LEN = 2
_RVC_BODY_LEN = 19
_RVC_FRAME_LEN = _RVC_HEADER_LEN + _RVC_BODY_LEN  # 21 bytes total
_RVC_SCALE = 0.01  # all int16 values are in units of 0.01 (deg or m/s^2)


@dataclass
class BNO085DriverConfig:
    port: str = "/dev/serial0"
    baudrate: int = 115200
    read_timeout: float = 0.1   # seconds; non-blocking poll


def _parse_rvc_frame(body: bytes) -> dict[str, float] | None:
    """Parse the 19-byte RVC body (after header bytes).

    Returns a dict with roll/pitch/yaw/accel_x/accel_y/accel_z and
    ``calibration_status = "rvc_active"``, or *None* if the checksum fails.

    Struct layout for the 19-byte body:
      B      - index (1 byte)
      hhhhhh - yaw, pitch, roll, x_accel, y_accel, z_accel (6 x int16 LE = 12 bytes)
      5x     - 5 reserved bytes
      B      - checksum (1 byte)
    Total: 1 + 12 + 5 + 1 = 19 bytes.
    """
    if len(body) != _RVC_BODY_LEN:
        return None

    # Checksum: low byte of sum of bytes [0..17] (exclude last byte = checksum)
    expected_checksum = sum(body[:-1]) & 0xFF
    if body[-1] != expected_checksum:
        logger.debug(
            "BNO085 RVC checksum mismatch: got 0x%02x expected 0x%02x",
            body[-1],
            expected_checksum,
        )
        return None

    # Unpack: 1 index byte + 6 signed int16 + 6 trailing bytes (5 reserved + 1 checksum, already validated)
    idx, yaw_raw, pitch_raw, roll_raw, ax_raw, ay_raw, az_raw = struct.unpack_from(
        "<Bhhhhhhxxxxxx", body
    )

    return {
        "roll": roll_raw * _RVC_SCALE,
        "pitch": pitch_raw * _RVC_SCALE,
        "yaw": yaw_raw * _RVC_SCALE,
        "accel_x": ax_raw * _RVC_SCALE,
        "accel_y": ay_raw * _RVC_SCALE,
        "accel_z": az_raw * _RVC_SCALE,
        "calibration_status": "rvc_active",
    }


def _read_rvc_frame_sync(serial_port) -> dict[str, float] | None:
    """Blocking read of one RVC frame from an open ``serial.Serial`` port.

    Scans the incoming byte stream for the 0xAA 0xAA header, then reads
    the 19-byte body.  Returns parsed orientation dict or *None* on timeout
    or checksum error.
    """
    # Search for header (scan at most 2 full frames worth of bytes)
    scan_limit = _RVC_FRAME_LEN * 2
    scanned = 0
    while scanned < scan_limit:
        b = serial_port.read(1)
        if not b:
            return None  # timeout
        scanned += 1
        if b[0] != 0xAA:
            continue
        b2 = serial_port.read(1)
        if not b2:
            return None
        scanned += 1
        if b2[0] != 0xAA:
            continue
        # Header found -- read body
        body = serial_port.read(_RVC_BODY_LEN)
        if len(body) < _RVC_BODY_LEN:
            return None
        return _parse_rvc_frame(bytes(body))
    return None


class BNO085Driver(HardwareDriver):
    """BNO085 IMU driver -- UART/RVC mode.

    Config keys (all optional):
      ``port``         : serial device path (default ``/dev/serial0``; override
                         with env var ``BNO085_PORT``)
      ``baudrate``     : baud rate (default 115200)
      ``read_timeout`` : per-read timeout in seconds (default 0.1)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        self._cfg = BNO085DriverConfig(
            port=cfg.get("port", os.environ.get("BNO085_PORT", "/dev/serial0")),
            baudrate=int(cfg.get("baudrate", 115200)),
            read_timeout=float(cfg.get("read_timeout", 0.1)),
        )
        self._serial = None
        self._last_orientation: dict[str, Any] | None = None
        self._last_read_ts: float | None = None
        self._cycle: int = 0
        self._valid_frames: int = 0  # count of successfully parsed frames

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:  # noqa: D401
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            self.initialized = True
            return
        # Lazy import: avoid import-time crash on non-Pi environments
        try:
            import serial  # noqa: PLC0415

            self._serial = await asyncio.to_thread(
                lambda: serial.Serial(
                    self._cfg.port,
                    self._cfg.baudrate,
                    timeout=self._cfg.read_timeout,
                )
            )
            logger.info(
                "BNO085 opened on %s @ %d baud (RVC mode)",
                self._cfg.port,
                self._cfg.baudrate,
            )
        except Exception as exc:
            logger.warning(
                "BNO085: failed to open %s -- %s. IMU will report uncalibrated.",
                self._cfg.port,
                exc,
            )
            self._serial = None
        self.initialized = True

    async def start(self) -> None:  # noqa: D401
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False
        if self._serial is not None:
            try:
                await asyncio.to_thread(self._serial.close)
            except Exception:
                pass
            self._serial = None

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": "bno085_imu",
            "initialized": self.initialized,
            "running": self.running,
            "port": self._cfg.port,
            "serial_open": (self._serial.is_open)
            if self._serial is not None
            else False,
            "valid_frames": self._valid_frames,
            "last_orientation": self._last_orientation,
            "last_read_age_s": (time.time() - self._last_read_ts)
            if self._last_read_ts
            else None,
            "simulation": is_simulation_mode(),
            "calibration_note": (
                "RVC mode: calibration level not exposed by protocol; "
                "status is 'rvc_active' once frames are received."
            ),
        }

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    async def read_orientation(self) -> dict[str, Any] | None:
        if not self.initialized:
            return None

        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            return self._sim_read()

        return await self._hw_read()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sim_read(self) -> dict[str, Any]:
        """Return a deterministic simulated orientation."""
        yaw = (self._cycle * 3) % 360
        roll = math.sin(self._cycle / 20) * 5
        pitch = math.cos(self._cycle / 25) * 3
        if self._cycle % 50 == 10:
            roll = 35.0 + random.uniform(0, 2)  # simulate unsafe tilt
        calibration_state = "calibrating" if self._cycle < 80 else "fully_calibrated"
        self._cycle += 1
        self._last_orientation = {
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81,
            "calibration_status": calibration_state,
        }
        self._last_read_ts = time.time()
        return self._last_orientation

    async def _hw_read(self) -> dict[str, Any] | None:
        """Read one RVC frame from the serial port (non-blocking via thread)."""
        if self._serial is None or not self._serial.is_open:
            # Port not available -- return last known reading or uncalibrated placeholder
            if self._last_orientation is None:
                self._last_orientation = {
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                    "accel_x": 0.0,
                    "accel_y": 0.0,
                    "accel_z": 0.0,
                    "calibration_status": "uncalibrated",
                }
            return self._last_orientation

        try:
            result = await asyncio.to_thread(_read_rvc_frame_sync, self._serial)
        except Exception as exc:
            logger.warning("BNO085 read error: %s", exc)
            return self._last_orientation  # stale but not None

        if result is not None:
            self._valid_frames += 1
            self._last_orientation = result
            self._last_read_ts = time.time()
        elif self._last_orientation is None:
            # No frame yet -- report uncalibrated placeholder so callers get
            # something meaningful rather than None / "unknown".
            self._last_orientation = {
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 0.0,
                "accel_x": 0.0,
                "accel_y": 0.0,
                "accel_z": 0.0,
                "calibration_status": "uncalibrated",
            }

        return self._last_orientation


__all__ = ["BNO085Driver"]
