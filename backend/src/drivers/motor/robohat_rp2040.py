"""RoboHAT RP2040 drive motor controller driver (T032).

SIM-safe UART stub to command Cytron MDDRC10 via RoboHAT firmware.
Implements minimal lifecycle and control methods; suitable for tests/CI.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

try:  # Lazy import for CI safety
    import serial  # type: ignore
except Exception:  # pragma: no cover - serial not required in SIM
    serial = None  # type: ignore

from ..base import HardwareDriver

logger = logging.getLogger(__name__)


@dataclass
class RoboHATMotorStatus:
    last_command_at: datetime | None = None
    last_error: str | None = None
    serial_connected: bool = False
    watchdog_latency_ms: float | None = None


class RoboHATRP2040Driver(HardwareDriver):
    """UART driver to interface with RoboHAT RP2040 firmware for drive motors."""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.port: str = (config or {}).get("serial_port", "/dev/ttyACM0")
        self.baud: int = int((config or {}).get("baud_rate", 115200))
        self._ser: Any = None
        self.status = RoboHATMotorStatus()

    async def initialize(self) -> None:
        sim_mode = (self.config or {}).get("SIM_MODE", None) or os.environ.get("SIM_MODE", "1")
        if sim_mode == "1" or serial is None:
            logger.info("RoboHAT driver SIM_MODE active; skipping serial open")
            self.status.serial_connected = False
            self.initialized = True
            return
        try:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.5, write_timeout=0.5)
            self.status.serial_connected = True
            self.initialized = True
        except Exception as e:  # pragma: no cover - hardware-specific
            self.status.last_error = str(e)
            logger.warning("RoboHAT serial open failed: %s", e)
            self.initialized = True  # allow tests to proceed in degraded mode

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        self.running = False
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:  # pragma: no cover
            pass

    async def health_check(self) -> dict[str, Any]:
        return {
            "driver": "robohat_rp2040",
            "serial_connected": self.status.serial_connected,
            "last_command_at": (
                self.status.last_command_at.isoformat()
                if self.status.last_command_at
                else None
            ),
            "last_error": self.status.last_error,
        }

    # ----- Drive controls -----

    async def send_drive(self, left: float, right: float) -> bool:
        """Send differential drive command (-1..1) to RoboHAT."""
        left = max(-1.0, min(1.0, float(left)))
        right = max(-1.0, min(1.0, float(right)))

        msg = {
            "cmd": "MOTOR_COMMAND",
            "params": {"left_speed": int(left * 100), "right_speed": int(right * 100)},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.status.last_command_at = datetime.now(UTC)

        # SIM path
        if self._ser is None or not getattr(self._ser, "is_open", False):
            logger.debug("[SIM] RoboHAT send_drive %s", msg)
            return True

        try:  # pragma: no cover - hardware-dependent
            payload = json.dumps(msg).encode("utf-8") + b"\n"
            self._ser.write(payload)
            self._ser.flush()
            ack_ok = await self._await_ack(timeout=0.2)
            if not ack_ok:
                self.status.last_error = "No ACK for MOTOR_COMMAND"
            return ack_ok
        except Exception as e:
            logger.error("RoboHAT send_drive failed: %s", e)
            self.status.last_error = str(e)
            return False

    async def emergency_stop(self) -> bool:
        msg = {"cmd": "EMERGENCY_STOP", "params": {}, "timestamp": datetime.now(UTC).isoformat()}
        self.status.last_command_at = datetime.now(UTC)

        if self._ser is None or not getattr(self._ser, "is_open", False):
            logger.debug("[SIM] RoboHAT emergency_stop %s", msg)
            return True
        try:  # pragma: no cover
            payload = json.dumps(msg).encode("utf-8") + b"\n"
            self._ser.write(payload)
            self._ser.flush()
            ack_ok = await self._await_ack(timeout=0.2)
            if not ack_ok:
                self.status.last_error = "No ACK for EMERGENCY_STOP"
            return ack_ok
        except Exception as e:
            logger.error("RoboHAT emergency_stop failed: %s", e)
            self.status.last_error = str(e)
            return False

    # ----- Internals -----

    async def _await_ack(self, timeout: float = 0.2) -> bool:
        """Wait briefly for an acknowledgment line from RoboHAT.

        Accepts either JSON like {"status":"ok"} / {"ack": true} / {"ok": true}
        or a plain text line containing OK/ACK (case-insensitive).
        """
        if self._ser is None or not getattr(self._ser, "is_open", False):
            return True

        deadline = time.monotonic() + max(0.01, timeout)
        while time.monotonic() < deadline:
            try:
                # Use a thread to avoid blocking the event loop on serial readline
                line: bytes = await asyncio.to_thread(self._readline_once)
            except Exception:  # pragma: no cover
                line = b""

            if line:
                if self._is_ack_line(line):
                    return True
                # On non-ack content, continue until deadline or ack arrives
            else:
                # Small cooperative pause to yield control
                await asyncio.sleep(0.005)
        return False

    def _readline_once(self) -> bytes:
        rl = getattr(self._ser, "readline", None)
        if callable(rl):
            return rl()
        read_until = getattr(self._ser, "read_until", None)
        if callable(read_until):
            return read_until(b"\n")
        # Fallback: attempt non-blocking read of some bytes
        read = getattr(self._ser, "read", None)
        if callable(read):
            try:
                data = read(256)
                if isinstance(data, bytes):
                    return data
            except Exception:  # pragma: no cover
                pass
        return b""

    def _is_ack_line(self, data: bytes) -> bool:
        try:
            text = data.decode("utf-8", errors="ignore").strip().lower()
        except Exception:
            return False

        if not text:
            return False

        # JSON forms
        if text.startswith("{") and text.endswith("}"):
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    if str(obj.get("status", "")).lower() == "ok":
                        return True
                    if bool(obj.get("ack", False)):
                        return True
                    if bool(obj.get("ok", False)):
                        return True
            except Exception:
                # fall through to text patterns
                pass

        # Textual ACK
        return ("ok" in text) or ("ack" in text)
