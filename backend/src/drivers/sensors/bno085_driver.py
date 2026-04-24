"""BNO085 IMU driver (T046) — UART/SHTP mode.

Communicates with a BNO085 via the SHTP protocol over UART at 3 Mbaud.
Uses the ``adafruit_bno08x`` library for protocol management including
soft reset, feature enable, and packet framing.

## SHTP vs RVC
The BNO085 PS1 pin determines the UART mode:
  - PS1 LOW  (default on most breakouts): **SHTP** — 3,000,000 baud, active
    protocol requiring init and feature enable.  Provides full sensor fusion,
    gyro, magnetometer, and per-subsystem calibration levels (0-3).
  - PS1 HIGH: **RVC** — 115,200 baud, auto-streams simplified orientation.
    No calibration registers exposed.

This driver targets **SHTP mode** and uses the Adafruit CircuitPython
BNO08X UART transport.

## Calibration status mapping
The SHTP protocol exposes magnetometer accuracy as an integer 0-3:
  0 → "uncalibrated"
  1 → "partial"
  2 → "calibrating"
  3 → "fully_calibrated"
These strings match the vocabulary consumed by ``sensor_manager.py``,
``navigation_service.py``, and the frontend dashboard.

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
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver

logger = logging.getLogger(__name__)

# Dedicated thread pool for BNO085 SHTP reads.  A size of 2 gives one active
# read plus one queued — enough headroom without ever exhausting the global
# asyncio thread pool (which is shared with GPS, INA3221, VL53L0X, etc.).
_BNO085_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bno085")

# SHTP calibration level → contract string
_SHTP_CAL_MAP: dict[int, str] = {
    0: "uncalibrated",
    1: "partial",
    2: "calibrating",
    3: "fully_calibrated",
}

# Maximum age (seconds) before a cached reading is downgraded to uncalibrated
_MAX_STALE_AGE_S = 5.0


@dataclass
class BNO085DriverConfig:
    port: str = "/dev/ttyAMA4"
    baudrate: int = 3_000_000
    # Shorter timeout so a non-responding sensor yields the thread quickly.
    # At 3 Mbaud, a full SHTP packet (≤256 B) arrives in <1 ms; 200 ms is
    # conservative but avoids the 1-second blocking seen with the old default.
    read_timeout: float = 0.2


def _quaternion_to_euler(i: float, j: float, k: float, real: float) -> tuple[float, float, float]:
    """Convert quaternion (i, j, k, real) to Euler angles (yaw, pitch, roll) in degrees.

    Uses ZYX aerospace convention (Tait-Bryan).  Returns yaw in [0, 360), pitch
    and roll in [-180, 180].
    """
    # Roll (X axis rotation)
    sinr_cosp = 2.0 * (real * i + j * k)
    cosr_cosp = 1.0 - 2.0 * (i * i + j * j)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    # Pitch (Y axis rotation)
    sinp = 2.0 * (real * j - k * i)
    sinp = max(-1.0, min(1.0, sinp))  # clamp for asin safety
    pitch = math.asin(sinp)

    # Yaw (Z axis rotation)
    siny_cosp = 2.0 * (real * k + i * j)
    cosy_cosp = 1.0 - 2.0 * (i * i + k * k)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    yaw_deg = math.degrees(yaw) % 360.0  # normalize to [0, 360)
    pitch_deg = math.degrees(pitch)
    roll_deg = math.degrees(roll)
    return yaw_deg, pitch_deg, roll_deg


def _read_shtp_sync(bno, valid_frames: int = 0) -> dict[str, Any] | None:
    """Blocking read of all enabled SHTP reports from a ``BNO08X_UART`` instance.

    Returns an orientation dict or ``None`` if the sensor has no data ready.
    Must be called from a worker thread (not the event loop).

    Uses the *Game Rotation Vector* report which provides stable heading based on
    gyro + accelerometer fusion only — no magnetometer required.  This avoids
    false calibration failures caused by motor-current magnetic interference.

    Calibration status reflects sensor warmup rather than magnetometer accuracy:
      - "calibrating":     fewer than 30 valid frames (gyro still integrating, ~6 s)
      - "fully_calibrated": 30 or more valid frames (gyro settled, heading reliable)
    """
    quat = bno.game_quaternion  # Game Rotation Vector — no magnetometer dependency
    if quat is None or quat[0] is None:
        return None

    # game_quaternion is (i, j, k, real)
    i, j, k, real = quat
    yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

    accel = bno.acceleration or (0.0, 0.0, 0.0)
    gyro = bno.gyro or (0.0, 0.0, 0.0)

    # Game rotation vector has no magnetometer accuracy field.
    # Report "calibrating" during the brief gyro warmup (~30 frames, ≈6 s at 5 Hz)
    # then "fully_calibrated" once the integration has settled.
    cal_str = "fully_calibrated" if valid_frames >= 30 else "calibrating"

    return {
        "roll": roll,
        "pitch": pitch,
        "yaw": yaw,
        "accel_x": accel[0],
        "accel_y": accel[1],
        "accel_z": accel[2],
        "gyro_x": gyro[0],
        "gyro_y": gyro[1],
        "gyro_z": gyro[2],
        "calibration_status": cal_str,
    }


class BNO085Driver(HardwareDriver):
    """BNO085 IMU driver — UART/SHTP mode at 3 Mbaud.

    Config keys (all optional):
      ``port``         : serial device path (default ``/dev/ttyAMA4``; override
                         with env var ``BNO085_PORT``)
      ``baudrate``     : baud rate (default 3000000)
      ``read_timeout`` : serial timeout in seconds (default 1.0)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        self._cfg = BNO085DriverConfig(
            port=cfg.get("port", os.environ.get("BNO085_PORT", "/dev/ttyAMA4")),
            baudrate=int(cfg.get("baudrate", 3_000_000)),
            read_timeout=float(cfg.get("read_timeout", 1.0)),
        )
        self._serial = None
        self._bno = None  # adafruit_bno08x BNO08X_UART instance
        self._lock = asyncio.Lock()  # serialize all hardware access
        self._last_orientation: dict[str, Any] | None = None
        self._last_read_ts: float | None = None
        self._cycle: int = 0
        self._valid_frames: int = 0
        self._consecutive_errors: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:  # noqa: D401
        if is_simulation_mode():
            self.initialized = True
            return

        try:
            loop = asyncio.get_running_loop()
            self._bno = await loop.run_in_executor(_BNO085_EXECUTOR, self._open_shtp)
            logger.info(
                "BNO085 SHTP initialized on %s @ %d baud",
                self._cfg.port,
                self._cfg.baudrate,
            )
        except Exception as exc:
            logger.warning(
                "BNO085: SHTP init failed on %s — %s. IMU will report uncalibrated.",
                self._cfg.port,
                exc,
            )
            self._bno = None
        self.initialized = True

    def _open_shtp(self):
        """Open serial port, create BNO08X_UART, enable reports (blocking)."""
        import serial  # noqa: PLC0415
        from adafruit_bno08x import (  # noqa: PLC0415
            BNO_REPORT_ACCELEROMETER,
            BNO_REPORT_GAME_ROTATION_VECTOR,
            BNO_REPORT_GYROSCOPE,
        )
        from adafruit_bno08x.uart import BNO08X_UART  # noqa: PLC0415

        uart = serial.Serial(
            self._cfg.port,
            self._cfg.baudrate,
            timeout=self._cfg.read_timeout,
        )
        self._serial = uart

        # Constructor performs soft reset (~1-2 s)
        bno = BNO08X_UART(uart)

        # Game Rotation Vector: gyro + accelerometer fusion only.
        # Deliberately avoids the magnetometer so motor-current magnetic
        # interference doesn't degrade heading quality or prevent calibration.
        bno.enable_feature(BNO_REPORT_GAME_ROTATION_VECTOR)
        bno.enable_feature(BNO_REPORT_ACCELEROMETER)
        bno.enable_feature(BNO_REPORT_GYROSCOPE)
        return bno

    async def start(self) -> None:  # noqa: D401
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False
        async with self._lock:
            self._bno = None
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
            "baudrate": self._cfg.baudrate,
            "mode": "SHTP",
            "serial_open": (self._serial is not None and self._serial.is_open),
            "shtp_connected": self._bno is not None,
            "valid_frames": self._valid_frames,
            "consecutive_errors": self._consecutive_errors,
            "last_orientation": self._last_orientation,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode(),
        }

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    async def read_orientation(self) -> dict[str, Any] | None:
        if not self.initialized:
            return None

        if is_simulation_mode():
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
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
            "calibration_status": calibration_state,
        }
        self._last_read_ts = time.time()
        return self._last_orientation

    async def _hw_read(self) -> dict[str, Any] | None:
        """Read SHTP reports from the BNO085 (serialized, non-blocking via thread).

        Uses the dedicated ``_BNO085_EXECUTOR`` so a slow/stuck read never
        exhausts the global asyncio thread pool.
        """
        if self._bno is None:
            return self._stale_or_placeholder()

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    _BNO085_EXECUTOR, _read_shtp_sync, self._bno, self._valid_frames
                )
            except Exception as exc:
                self._consecutive_errors += 1
                if self._consecutive_errors == 1 or self._consecutive_errors % 30 == 0:
                    logger.warning(
                        "BNO085 SHTP read error (%d consecutive): %s",
                        self._consecutive_errors,
                        exc,
                    )
                # After many consecutive failures, attempt re-init
                if self._consecutive_errors >= 10:
                    logger.warning(
                        "BNO085: %d consecutive errors, attempting re-init",
                        self._consecutive_errors,
                    )
                    await self._attempt_reinit()
                return self._stale_or_placeholder()

        if result is not None:
            if self._valid_frames == 0:
                logger.info(
                    "BNO085 first SHTP frame on %s (yaw=%.1f° pitch=%.1f° roll=%.1f° cal=%s)",
                    self._cfg.port,
                    result["yaw"],
                    result["pitch"],
                    result["roll"],
                    result["calibration_status"],
                )
            self._consecutive_errors = 0
            self._valid_frames += 1
            self._last_orientation = result
            self._last_read_ts = time.time()
        else:
            self._consecutive_errors += 1
            if self._consecutive_errors == 30:
                logger.warning(
                    "BNO085 on %s: no SHTP data after %d read cycles. "
                    "Check sensor power and UART4 wiring (GPIO12=TX, GPIO13=RX).",
                    self._cfg.port,
                    self._consecutive_errors,
                )

        return self._stale_or_placeholder()

    def _stale_or_placeholder(self) -> dict[str, Any]:
        """Return last orientation if fresh enough, otherwise an uncalibrated placeholder."""
        if (
            self._last_orientation is not None
            and self._last_read_ts is not None
            and (time.time() - self._last_read_ts) < _MAX_STALE_AGE_S
        ):
            return self._last_orientation

        # Data too old or never received — report uncalibrated so navigation
        # does not trust stale heading
        return {
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 0.0,
            "gyro_x": 0.0,
            "gyro_y": 0.0,
            "gyro_z": 0.0,
            "calibration_status": "uncalibrated",
        }

    async def _attempt_reinit(self) -> None:
        """Try to re-initialize the SHTP connection after repeated failures."""
        try:
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
            self._bno = None
            loop = asyncio.get_running_loop()
            self._bno = await loop.run_in_executor(_BNO085_EXECUTOR, self._open_shtp)
            self._consecutive_errors = 0
            logger.info("BNO085 SHTP re-initialized successfully on %s", self._cfg.port)
        except Exception as exc:
            logger.warning("BNO085 re-init failed: %s", exc)
            self._bno = None


__all__ = ["BNO085Driver"]
