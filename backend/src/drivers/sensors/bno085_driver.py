"""BNO085 IMU driver (T046) — UART, SHTP or RVC transport.

## SHTP vs RVC
The BNO085 PS1 pin determines the UART mode, in hardware:
  - PS1 LOW  (default on most breakouts): **SHTP** — 3,000,000 baud, active
    protocol requiring init and feature enable.  Provides full sensor fusion,
    gyro, magnetometer, and per-subsystem calibration levels (0-3).  Driven via
    the ``adafruit_bno08x`` library.
  - PS1 HIGH: **RVC** — 115,200 baud, auto-streams a fixed 19-byte orientation
    frame at 100 Hz.  No gyro, no calibration registers.  Parsed in-tree by
    ``parse_rvc_frame`` / ``RvcStream``; no external library needed.

Both are supported.  ``mode="auto"`` (the default) probes RVC first — that probe
is passive, listening only, so it cannot disturb a sensor that is really in SHTP
mode — then falls back to SHTP.  Set ``mode`` explicitly in ``hardware.yaml`` to
skip detection.

Mismatching the strap against the driver is not a silent failure but it is an
opaque one: SHTP against an RVC-mode sensor reports ``Didn't find packet end``,
because bytes do arrive, they just aren't SHTP packets.

## Calibration status mapping
The SHTP protocol exposes magnetometer accuracy as an integer 0-3:
  0 → "uncalibrated"
  1 → "partial"
  2 → "calibrating"
  3 → "fully_calibrated"
These strings match the vocabulary consumed by ``sensor_manager.py``,
``navigation_service.py``, and the frontend dashboard.

Both transports report status from stream uptime rather than magnetometer
accuracy: this driver uses the Game Rotation Vector (SHTP) or RVC, neither of
which depends on the magnetometer, deliberately, so that motor-current magnetic
interference cannot degrade heading or block calibration.

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
import uuid
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

# ----------------------------------------------------------------------
# UART-RVC framing (PS1 HIGH)
# ----------------------------------------------------------------------
# Fixed 19-byte frame auto-streamed at 100 Hz.  Layout:
#   0-1  0xAA 0xAA header      2     index (rolling)
#   3-8  yaw/pitch/roll        int16 LE, 0.01 deg each
#   9-14 accel X/Y/Z           int16 LE, 0.0098 m/s^2 each
#   15-17 reserved             18    checksum = sum(bytes 2..17) & 0xFF
_RVC_HEADER = b"\xaa\xaa"
_RVC_FRAME_LEN = 19
_RVC_BAUD = 115_200
_RVC_ANGLE_SCALE = 0.01  # int16 -> degrees
_RVC_ACCEL_SCALE = 0.0098  # int16 -> m/s^2
# Cap on unparsed bytes retained between reads.  Garbage (wrong baud, floating
# line) must never accumulate without bound.
_RVC_MAX_BUFFER = 512


def parse_rvc_frame(frame: bytes) -> dict[str, Any] | None:
    """Decode one 19-byte UART-RVC frame.

    Returns an orientation dict matching the same contract as the SHTP path, or
    ``None`` if the frame is the wrong length, lacks the 0xAAAA header, or fails
    its checksum.  Pure function — no I/O, no driver state.
    """
    if len(frame) != _RVC_FRAME_LEN:
        return None
    if frame[0] != 0xAA or frame[1] != 0xAA:
        return None
    if (sum(frame[2:18]) & 0xFF) != frame[18]:
        return None

    yaw_raw, pitch_raw, roll_raw, ax, ay, az = struct.unpack_from("<hhhhhh", frame, 3)

    # Yaw is a compass heading and is normalised to [0, 360) to match the SHTP
    # path.  Pitch and roll are signed tilt angles and must keep their sign —
    # the FR-022 tilt cutoff depends on it.
    return {
        "roll": roll_raw * _RVC_ANGLE_SCALE,
        "pitch": pitch_raw * _RVC_ANGLE_SCALE,
        "yaw": (yaw_raw * _RVC_ANGLE_SCALE) % 360.0,
        "accel_x": ax * _RVC_ACCEL_SCALE,
        "accel_y": ay * _RVC_ACCEL_SCALE,
        "accel_z": az * _RVC_ACCEL_SCALE,
        # RVC carries no angular rate. Keys are held at 0.0 so downstream
        # consumers see a stable schema across both transport modes.
        "gyro_x": 0.0,
        "gyro_y": 0.0,
        "gyro_z": 0.0,
        "index": frame[2],
    }


class RvcStream:
    """Resynchronising byte-stream reader for UART-RVC frames.

    Serial reads chop the 100 Hz stream at arbitrary offsets and a mid-frame
    connection starts partway through a frame, so the reader keeps a buffer,
    hunts for the 0xAAAA header, and skips past false headers or corrupt frames
    without stalling on the bytes that follow them.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        """Append raw bytes and return every complete, valid frame decoded."""
        if data:
            self._buf.extend(data)

        out: list[dict[str, Any]] = []
        buf = self._buf
        consumed = 0

        while True:
            start = buf.find(_RVC_HEADER, consumed)
            if start < 0:
                # No header at all. Retain a single trailing byte in case it is
                # the first half of a header split across this read boundary.
                consumed = max(consumed, len(buf) - 1)
                break
            if len(buf) - start < _RVC_FRAME_LEN:
                consumed = start  # partial frame; wait for the rest
                break

            parsed = parse_rvc_frame(bytes(buf[start : start + _RVC_FRAME_LEN]))
            if parsed is not None:
                out.append(parsed)
                consumed = start + _RVC_FRAME_LEN
            else:
                # False header or corrupt frame — step past this header only, so
                # a genuine frame overlapping these bytes is still found.
                consumed = start + 2

        if consumed:
            del buf[:consumed]
        if len(buf) > _RVC_MAX_BUFFER:
            del buf[:-_RVC_FRAME_LEN]
        return out


@dataclass
class BNO085DriverConfig:
    port: str = "/dev/ttyAMA4"
    baudrate: int = 3_000_000
    # Shorter timeout so a non-responding sensor yields the thread quickly.
    # At 3 Mbaud, a full SHTP packet (≤256 B) arrives in <1 ms; 200 ms is
    # conservative but avoids the 1-second blocking seen with the old default.
    read_timeout: float = 0.2
    # Transport selection. The BNO085 PS1 pin fixes this in hardware:
    #   "shtp" — PS1 LOW,  3 Mbaud, active protocol
    #   "rvc"  — PS1 HIGH, 115200 baud, auto-streaming
    #   "auto" — probe RVC first (cheap, passive), fall back to SHTP
    mode: str = "auto"
    rvc_baudrate: int = _RVC_BAUD
    # Seconds to listen for a valid RVC frame before declaring the probe failed.
    # At 100 Hz a frame arrives every 10 ms; 1.5 s tolerates a mid-frame start
    # plus the sensor's power-on settling.
    rvc_probe_timeout: float = 1.5


def _tracked_bno08x_uart_class(base_cls: type, game_report_id: int) -> type:
    """Wrap ``BNO08X_UART`` with a counter for genuinely processed game reports."""

    class ReportTrackingBNO08XUART(base_cls):
        def __init__(self, *args, **kwargs):
            # The Adafruit constructor can process packets, so initialize this
            # before delegating to it.
            self._game_report_sequence = 0
            super().__init__(*args, **kwargs)

        @property
        def game_report_sequence(self) -> int:
            return self._game_report_sequence

        def _process_report(self, report_id: int, report_bytes: bytearray) -> None:
            super()._process_report(report_id, report_bytes)
            if report_id == game_report_id:
                self._game_report_sequence += 1

    return ReportTrackingBNO08XUART


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
    # ``game_quaternion`` remains populated with the last library-cached value
    # after the UART stream stops.  Only a counter advanced by _process_report
    # proves that this property access consumed a new physical sensor report.
    report_sequence_before = getattr(bno, "game_report_sequence", None)
    quat = bno.game_quaternion  # Game Rotation Vector — no magnetometer dependency
    report_sequence_after = getattr(bno, "game_report_sequence", None)
    if (
        not isinstance(report_sequence_before, int)
        or not isinstance(report_sequence_after, int)
        or report_sequence_after <= report_sequence_before
    ):
        return None
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
    """BNO085 IMU driver — UART, SHTP (3 Mbaud) or RVC (115200) transport.

    The active transport is fixed in hardware by the PS1 strap; ``mode="auto"``
    (the default) detects which one the sensor is actually using.

    Config keys (all optional):
      ``port``         : serial device path (default ``/dev/ttyAMA4``; override
                         with env var ``BNO085_PORT``)
      ``mode``         : ``"auto"`` | ``"rvc"`` | ``"shtp"`` (default ``"auto"``)
      ``baudrate``     : SHTP baud rate (default 3000000)
      ``rvc_baudrate`` : RVC baud rate (default 115200)
      ``read_timeout`` : serial timeout in seconds (default 1.0)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        self._cfg = BNO085DriverConfig(
            port=cfg.get("port", os.environ.get("BNO085_PORT", "/dev/ttyAMA4")),
            baudrate=int(cfg.get("baudrate", 3_000_000)),
            read_timeout=float(cfg.get("read_timeout", 1.0)),
            mode=str(cfg.get("mode", os.environ.get("BNO085_MODE", "auto"))),
            rvc_baudrate=int(cfg.get("rvc_baudrate", _RVC_BAUD)),
        )
        self._serial = None
        self._bno = None  # adafruit_bno08x BNO08X_UART instance
        self._rvc_serial = None  # pyserial handle when running in RVC mode
        self._rvc_stream = RvcStream()
        self._mode: str | None = None  # set once a transport opens successfully
        self._lock = asyncio.Lock()  # serialize all hardware access
        self._last_orientation: dict[str, Any] | None = None
        self._last_read_ts: float | None = None
        self._cycle: int = 0
        self._valid_frames: int = 0
        self._consecutive_errors: int = 0
        # Simulation has one stable epoch for the lifetime of this driver.
        # Hardware epochs are assigned only after a successful open/re-open.
        self._imu_epoch_id: str | None = (
            uuid.uuid4().hex if is_simulation_mode() else None
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:  # noqa: D401
        if is_simulation_mode():
            self.initialized = True
            return

        self._reset_imu_session()
        loop = asyncio.get_running_loop()
        mode = (self._cfg.mode or "auto").lower()
        errors: list[str] = []

        # RVC is probed first in "auto" because it is passive: it only listens
        # for auto-streamed frames and never writes to the sensor, so a failed
        # probe cannot disturb a device that is actually in SHTP mode. Opening
        # SHTP, by contrast, issues a soft reset.
        for candidate in (("rvc", "shtp") if mode == "auto" else (mode,)):
            try:
                if candidate == "rvc":
                    self._rvc_serial = await loop.run_in_executor(
                        _BNO085_EXECUTOR, self._open_rvc
                    )
                else:
                    self._bno = await loop.run_in_executor(_BNO085_EXECUTOR, self._open_shtp)
                self._mode = candidate
                self._imu_epoch_id = uuid.uuid4().hex
                logger.info(
                    "BNO085 %s initialized on %s @ %d baud",
                    candidate.upper(),
                    self._cfg.port,
                    self._cfg.rvc_baudrate if candidate == "rvc" else self._cfg.baudrate,
                )
                break
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
                self._close_transports()

        if self._mode is None:
            logger.warning(
                "BNO085: init failed on %s (%s). IMU will report uncalibrated. "
                "Check the PS1 strap — HIGH selects RVC @115200, LOW selects SHTP @3M.",
                self._cfg.port,
                "; ".join(errors),
            )
        self.initialized = True

    def _open_rvc(self):
        """Open the port at RVC baud and verify real frames arrive (blocking).

        Purely passive — nothing is written to the sensor, so probing this mode
        is safe even when the device turns out to be in SHTP mode.  Raises if no
        valid frame appears within ``rvc_probe_timeout``, which is what lets
        ``mode="auto"`` fall through to SHTP.
        """
        import serial  # noqa: PLC0415

        uart = serial.Serial(
            self._cfg.port,
            self._cfg.rvc_baudrate,
            timeout=self._cfg.read_timeout,
        )
        try:
            uart.reset_input_buffer()
            self._rvc_stream = RvcStream()
            deadline = time.monotonic() + self._cfg.rvc_probe_timeout
            while time.monotonic() < deadline:
                chunk = uart.read(max(1, uart.in_waiting or _RVC_FRAME_LEN))
                if chunk and self._rvc_stream.feed(chunk):
                    return uart
            raise RuntimeError(
                f"no valid RVC frame within {self._cfg.rvc_probe_timeout:.1f}s "
                f"at {self._cfg.rvc_baudrate} baud"
            )
        except Exception:
            try:
                uart.close()
            except Exception:
                pass
            raise

    def _read_rvc_sync(self, valid_frames: int = 0) -> dict[str, Any] | None:
        """Drain buffered RVC frames and return the newest (blocking).

        The sensor free-runs at 100 Hz while the sensor manager polls far more
        slowly, so several frames are usually waiting.  Only the most recent is
        returned — older ones are stale orientation by definition.  Returns
        ``None`` when no complete valid frame is available.
        """
        uart = self._rvc_serial
        if uart is None:
            return None

        chunk = uart.read(max(1, uart.in_waiting or _RVC_FRAME_LEN))
        frames = self._rvc_stream.feed(chunk or b"")
        if not frames:
            return None

        latest = frames[-1]
        # RVC exposes no calibration registers, so status mirrors the SHTP path:
        # derived from how long the stream has been running rather than from the
        # magnetometer (which this driver deliberately ignores anyway).
        return {
            **{k: v for k, v in latest.items() if k != "index"},
            "calibration_status": "fully_calibrated" if valid_frames >= 30 else "calibrating",
        }

    def _close_transports(self) -> None:
        """Close any open serial handles and drop protocol state."""
        for attr in ("_serial", "_rvc_serial"):
            handle = getattr(self, attr, None)
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
            setattr(self, attr, None)
        self._bno = None
        self._rvc_stream = RvcStream()

    def _open_shtp(self):
        """Open serial port, create BNO08X_UART, enable reports (blocking)."""
        import serial  # noqa: PLC0415
        from adafruit_bno08x import (  # noqa: PLC0415
            BNO_REPORT_ACCELEROMETER,
            BNO_REPORT_GAME_ROTATION_VECTOR,
            BNO_REPORT_GYROSCOPE,
        )
        from adafruit_bno08x.uart import BNO08X_UART as AdafruitBNO08XUART  # noqa: PLC0415

        uart = serial.Serial(
            self._cfg.port,
            self._cfg.baudrate,
            timeout=self._cfg.read_timeout,
        )
        self._serial = uart

        # Constructor performs soft reset (~1-2 s)
        tracked_uart_cls = _tracked_bno08x_uart_class(
            AdafruitBNO08XUART,
            BNO_REPORT_GAME_ROTATION_VECTOR,
        )
        bno = tracked_uart_cls(uart)

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
            await asyncio.to_thread(self._close_transports)
            self._mode = None

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": "bno085_imu",
            "initialized": self.initialized,
            "running": self.running,
            "port": self._cfg.port,
            "baudrate": self._cfg.baudrate,
            "mode": (self._mode or "none").upper(),
            "connected": self._mode is not None,
            "serial_open": any(
                h is not None and h.is_open for h in (self._serial, self._rvc_serial)
            ),
            "shtp_connected": self._bno is not None,
            "valid_frames": self._valid_frames,
            "consecutive_errors": self._consecutive_errors,
            "imu_epoch_id": self._imu_epoch_id,
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
            "monotonic_received_s": time.monotonic(),
            "cached": False,
            "imu_epoch_id": self._imu_epoch_id,
        }
        self._last_read_ts = time.time()
        return self._last_orientation

    async def _hw_read(self) -> dict[str, Any] | None:
        """Read SHTP reports from the BNO085 (serialized, non-blocking via thread).

        Uses the dedicated ``_BNO085_EXECUTOR`` so a slow/stuck read never
        exhausts the global asyncio thread pool.
        """
        if self._mode is None:
            return self._stale_or_placeholder()

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                if self._mode == "rvc":
                    result = await loop.run_in_executor(
                        _BNO085_EXECUTOR, self._read_rvc_sync, self._valid_frames
                    )
                else:
                    result = await loop.run_in_executor(
                        _BNO085_EXECUTOR, _read_shtp_sync, self._bno, self._valid_frames
                    )
            except Exception as exc:
                self._consecutive_errors += 1
                if self._consecutive_errors == 1 or self._consecutive_errors % 30 == 0:
                    logger.warning(
                        "BNO085 %s read error (%d consecutive): %s",
                        (self._mode or "none").upper(),
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
                    "BNO085 first %s frame on %s (yaw=%.1f° pitch=%.1f° roll=%.1f° cal=%s)",
                    (self._mode or "none").upper(),
                    self._cfg.port,
                    result["yaw"],
                    result["pitch"],
                    result["roll"],
                    result["calibration_status"],
                )
            self._consecutive_errors = 0
            self._valid_frames += 1
            result = {
                **result,
                "monotonic_received_s": time.monotonic(),
                "cached": False,
                "imu_epoch_id": self._imu_epoch_id,
            }
            self._last_orientation = result
            self._last_read_ts = time.time()
            return result
        else:
            self._consecutive_errors += 1
            if self._consecutive_errors == 30:
                logger.warning(
                    "BNO085 on %s: no %s data after %d read cycles. "
                    "Check sensor power and UART4 wiring (GPIO12=TX, GPIO13=RX).",
                    self._cfg.port,
                    (self._mode or "none").upper(),
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
            return {**self._last_orientation, "cached": True}

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
            "monotonic_received_s": None,
            "cached": True,
            "imu_epoch_id": self._imu_epoch_id,
        }

    def _reset_imu_session(self) -> None:
        """Discard readings and identity from the previous physical IMU session."""
        self._last_orientation = None
        self._last_read_ts = None
        self._valid_frames = 0
        self._consecutive_errors = 0
        self._imu_epoch_id = None
        self._rvc_stream = RvcStream()

    async def _attempt_reinit(self) -> None:
        """Try to re-initialize the SHTP connection after repeated failures."""
        previous = self._mode
        self._close_transports()
        self._mode = None
        await self.initialize()
        if self._mode is not None:
            self._consecutive_errors = 0
            logger.info(
                "BNO085 re-initialized successfully on %s (%s)",
                self._cfg.port,
                self._mode.upper(),
            )
        else:
            logger.warning(
                "BNO085 re-init failed on %s (previous mode: %s)",
                self._cfg.port,
                previous or "none",
            )


__all__ = ["BNO085Driver"]
