"""Text protocol bridge for the RoboHAT RP2040 control board.

The bundled CircuitPython firmware (`robohat-rp2040-code/code.py`) exposes a
human-readable command set on its USB serial interface.  Earlier iterations of
the backend spoke a JSON RPC dialect which the current firmware rejects, so the
communication layer has to emit the same text commands you would type over a
serial console (e.g. ``rc=disable``, ``pwm,1500,1600``).

This module keeps the async façade expected by the FastAPI endpoints while
performing the minimal blocking serial I/O in tiny, protected critical sections.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import serial

logger = logging.getLogger(__name__)


@dataclass
class RoboHATStatus:
    """RoboHAT firmware status"""
    firmware_version: str = "unknown"
    uptime_seconds: int = 0
    watchdog_active: bool = False
    last_watchdog_echo: Optional[str] = None
    watchdog_latency_ms: float = 0.0
    serial_connected: bool = False
    error_count: int = 0
    last_error: Optional[str] = None
    motor_controller_ok: bool = False
    encoder_feedback_ok: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "firmware_version": self.firmware_version,
            "uptime_seconds": self.uptime_seconds,
            "watchdog_active": self.watchdog_active,
            "last_watchdog_echo": self.last_watchdog_echo,
            "watchdog_latency_ms": self.watchdog_latency_ms,
            "serial_connected": self.serial_connected,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "motor_controller_ok": self.motor_controller_ok,
            "encoder_feedback_ok": self.encoder_feedback_ok,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "health_status": self.get_health_status()
        }
    
    def get_health_status(self) -> str:
        """Get overall health status"""
        if not self.serial_connected:
            return "disconnected"
        if self.error_count > 10:
            return "fault"
        if not self.watchdog_active or not self.motor_controller_ok:
            return "warning"
        return "healthy"


class RoboHATService:
    """RoboHAT RP2040 serial bridge service"""
    
    def __init__(self, serial_port: str = "/dev/ttyACM0", baud_rate: int = 115200):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.serial_conn: Optional[serial.Serial] = None
        self.status = RoboHATStatus()
        self.running = False
        self.watchdog_task: Optional[asyncio.Task] = None
        self.read_task: Optional[asyncio.Task] = None
        self._serial_lock = asyncio.Lock()
        self._rc_enabled = True
        self._usb_control_requested = False
        self._pending_rc_state: Optional[bool] = None
        self._pending_rc_since: float = 0.0
        self._last_status_at: float = 0.0
        
    async def initialize(self) -> bool:
        """Initialize RoboHAT serial connection"""
        try:
            logger.info(f"Initializing RoboHAT service on {self.serial_port} at {self.baud_rate} baud")
            
            # Open serial connection
            self.serial_conn = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                timeout=1.0,
                write_timeout=1.0
            )
            
            # Wait for connection to stabilize
            await asyncio.sleep(2.0)

            # Flush any banner/boot messages so we begin with a clean buffer
            self._drain_serial_buffer()

            # Place the firmware in USB (backend) control mode
            await self._set_rc_enabled(False, force=True)

            self.status.serial_connected = True
            self.running = True

            # Start background tasks
            self.watchdog_task = asyncio.create_task(self._watchdog_loop())
            self.read_task = asyncio.create_task(self._read_loop())

            logger.info("RoboHAT service initialized successfully")
            return True
            
        except serial.SerialException as e:
            logger.error(f"Failed to initialize RoboHAT service: {e}")
            self.status.serial_connected = False
            self.status.last_error = str(e)
            return False
        except Exception as e:
            logger.error(f"Unexpected error initializing RoboHAT: {e}")
            self.status.last_error = str(e)
            return False
    
    async def _send_line(self, line: str) -> bool:
        """Send a raw line to the RoboHAT firmware."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        message = (line.rstrip("\r\n") + "\n").encode("utf-8")

        try:
            async with self._serial_lock:
                await asyncio.to_thread(self.serial_conn.write, message)
                await asyncio.to_thread(self.serial_conn.flush)
            return True
        except Exception as exc:  # pragma: no cover - hardware error path
            logger.error(f"Failed to send RoboHAT command line '%s': %s", line, exc)
            self.status.error_count += 1
            self.status.last_error = str(exc)
            return False

    def _drain_serial_buffer(self) -> None:
        """Synchronously drain any pending bytes from the serial buffer."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        try:
            # Read until buffer empty; keep the last status to process quickly
            while self.serial_conn.in_waiting:
                raw = self.serial_conn.readline()
                line = raw.decode("utf-8", errors="ignore").strip()
                if line:
                    self._process_line(line)
        except Exception:
            # Non-fatal – buffer draining is best effort
            pass

    def _mark_rc_state(self, enabled: bool) -> None:
        """Track the latest RC enable/disable state acknowledgement from firmware."""
        self._rc_enabled = enabled
        if self._pending_rc_state is not None:
            if self._pending_rc_state == enabled:
                self._pending_rc_state = None
                self._pending_rc_since = 0.0
                if enabled:
                    # An explicit enable acknowledgement corresponds to a backend request
                    self._usb_control_requested = False
            else:
                logger.warning(
                    "RoboHAT reported RC %s while backend awaited %s",
                    "enabled" if enabled else "disabled",
                    "enabled" if self._pending_rc_state else "disabled",
                )
                self._pending_rc_state = None
                self._pending_rc_since = 0.0

    async def _set_rc_enabled(self, enabled: bool, *, force: bool = False) -> None:
        """Toggle RC passthrough on the firmware so USB commands take over."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        # Record our desired control mode so the watchdog maintains it.
        self._usb_control_requested = not enabled

        if not force:
            if self._pending_rc_state is not None and self._pending_rc_state == enabled:
                return
            if self._pending_rc_state is None and self._rc_enabled == enabled:
                return

        cmd = "rc=enable" if enabled else "rc=disable"
        if await self._send_line(cmd):
            self._pending_rc_state = enabled
            self._pending_rc_since = time.monotonic()
        else:
            self._pending_rc_state = None
            self._pending_rc_since = 0.0
    
    async def _watchdog_loop(self):
        """Periodic watchdog ping loop"""
        while self.running:
            try:
                # When USB control is active, periodically refresh the neutral
                # PWM command so the firmware keeps RC disabled.
                await self._maintain_usb_control()

                await asyncio.sleep(1.0)

                now = time.monotonic()
                if self._last_status_at:
                    delta = now - self._last_status_at
                    self.status.watchdog_latency_ms = delta * 1000.0
                    self.status.watchdog_active = delta < 3.0
                else:
                    self.status.watchdog_active = False
                    self.status.watchdog_latency_ms = 0.0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog loop error: {e}")
                self.status.watchdog_active = False
                await asyncio.sleep(1.0)

    async def _maintain_usb_control(self) -> None:
        """Keep RoboHAT in USB control mode and feed neutral PWM when active."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return

        if not self._usb_control_requested:
            return

        if self._rc_enabled:
            await self._set_rc_enabled(False)
            return

        if self._pending_rc_state is not None:
            if (time.monotonic() - self._pending_rc_since) > 1.0:
                logger.warning("RoboHAT RC disable acknowledgement still pending; retrying command")
                await self._set_rc_enabled(False, force=True)
            return

        await self._send_line("pwm,1500,1500")

    async def _wait_for_usb_control(self, timeout: float = 0.75) -> bool:
        """Block until the firmware confirms USB control or timeout expires."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._rc_enabled and self._pending_rc_state is None:
                return True
            await asyncio.sleep(0.02)

        logger.warning("Timed out waiting for RoboHAT to acknowledge USB control")
        return False

    async def _ensure_usb_control(self, *, timeout: float = 0.75, retries: int = 1) -> bool:
        """Ensure RoboHAT is in USB control mode, retrying if acknowledgements lag."""
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        attempts = max(1, retries + 1)
        for attempt in range(attempts):
            try:
                await self._set_rc_enabled(False, force=attempt > 0)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Attempt %d/%d to disable RC control failed: %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
            adjusted_timeout = timeout + 0.1 * attempt
            if await self._wait_for_usb_control(timeout=adjusted_timeout):
                self.status.last_error = None
                return True
            await asyncio.sleep(0.05)

        logger.warning("Unable to obtain RoboHAT USB control after %d attempts", attempts)
        self.status.motor_controller_ok = False
        self.status.last_error = "usb_control_unavailable"
        return False
    
    async def _read_loop(self):
        """Continuous read loop for RoboHAT messages"""
        while self.running:
            try:
                line = None
                if self.serial_conn and self.serial_conn.is_open and self.serial_conn.in_waiting:
                    raw = await asyncio.to_thread(self.serial_conn.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()

                if line:
                    self._process_line(line)

                await asyncio.sleep(0.02)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Read loop error: {e}")
                await asyncio.sleep(0.1)
    
    def _process_line(self, line: str) -> None:
        """Parse human-readable firmware messages and update status fields."""
        if not line:
            return

        line_lower = line.lower()

        if line_lower.startswith("[status]"):
            try:
                brace_index = line.index("{")
                payload = json.loads(line[brace_index:])
            except Exception as exc:
                logger.warning("Failed to parse RoboHAT status payload '%s': %s", line, exc)
                return
            self._last_status_at = time.monotonic()
            if isinstance(payload.get("uptime_seconds"), (int, float)):
                self.status.uptime_seconds = int(payload["uptime_seconds"])
            rc_enabled = bool(payload.get("rc_enabled", self._rc_enabled))
            if rc_enabled != self._rc_enabled:
                self._mark_rc_state(rc_enabled)
            self.status.motor_controller_ok = not rc_enabled
            self.status.encoder_feedback_ok = payload.get("encoder") is not None
            self.status.last_watchdog_echo = "status"
            return

        if "rc enabled" in line_lower or "timeout" in line_lower and "rc mode" in line_lower:
            self._mark_rc_state(True)
            self._last_status_at = time.monotonic()
            logger.info("RoboHAT reported RC mode active")
            return

        if "rc disabled" in line_lower:
            self._mark_rc_state(False)
            self._last_status_at = time.monotonic()
            logger.info("RoboHAT reported USB control active")
            return

        if line_lower.startswith("[usb] pwm"):
            self._last_status_at = time.monotonic()
            self.status.motor_controller_ok = True
            self.status.last_watchdog_echo = "pwm_ack"
            return

        if line_lower.startswith("[usb] invalid"):
            # The backend attempted an unsupported command earlier. Count it once.
            if "pwm" in line_lower:
                self._mark_rc_state(True)
            logger.warning("RoboHAT rejected command: %s", line)
            self.status.motor_controller_ok = False
            self.status.error_count += 1
            self.status.last_error = line
            return

        if line_lower.startswith("\u25b6") or line_lower.startswith("▶"):
            # Firmware banner – useful for firmware version detection.
            self.status.firmware_version = line.strip()
            return

        if line_lower.startswith("[rc]"):
            # Heartbeat from firmware – keep as last echo.
            self.status.last_watchdog_echo = line
            self._last_status_at = time.monotonic()
            return

        # For everything else, keep a debug breadcrumb without polluting logs.
        logger.debug("RoboHAT: %s", line)
    
    async def send_motor_command(self, left_speed: float, right_speed: float) -> bool:
        """Send motor command to RoboHAT"""
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        if not await self._ensure_usb_control(timeout=0.9, retries=2):
            return False

        steer_us, throttle_us = self._mix_arcade_to_pwm(left_speed, right_speed)
        ok = await self._send_line(f"pwm,{steer_us},{throttle_us}")

        if ok:
            self.status.motor_controller_ok = True
            self.status.last_watchdog_echo = f"pwm:{steer_us}/{throttle_us}"
            self.status.last_error = None
        else:
            self.status.motor_controller_ok = False
            self.status.last_error = "pwm_send_failed"
        return ok
    
    async def send_blade_command(self, active: bool, speed: float = 1.0) -> bool:
        """Send blade motor command to RoboHAT"""
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        if not await self._ensure_usb_control(timeout=0.9, retries=2):
            return False
        command = "blade=on" if active and speed > 0 else "blade=off"
        ok = await self._send_line(command)
        if ok and not active:
            self.status.last_watchdog_echo = "blade:off"
        elif ok:
            self.status.last_watchdog_echo = "blade:on"
            self.status.last_error = None
        else:
            self.status.last_error = "blade_command_failed"
        return ok
    
    async def emergency_stop(self) -> bool:
        """Send emergency stop command to RoboHAT"""
        logger.critical("Sending emergency stop to RoboHAT")
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        usb_ready = await self._ensure_usb_control(timeout=0.6, retries=2)
        if not usb_ready:
            logger.warning("Emergency stop proceeding without USB control acknowledgement")
        ok = await self._send_line("pwm,1500,1500")
        ok = await self._send_line("blade=off") and ok
        self.status.motor_controller_ok = False
        self.status.last_watchdog_echo = "emergency_stop"
        if not ok:
            self.status.last_error = "emergency_stop_failed"
        return ok
    
    async def clear_emergency(self) -> bool:
        """Clear emergency stop on RoboHAT"""
        logger.info("Clearing emergency stop on RoboHAT")
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        if not await self._ensure_usb_control(timeout=0.9, retries=2):
            return False
        ok = await self._send_line("rc=disable")
        if not ok:
            self.status.last_error = "clear_emergency_failed"
        else:
            self.status.last_error = None
        return ok
    
    def get_status(self) -> RoboHATStatus:
        """Get current RoboHAT status"""
        self.status.timestamp = datetime.now(timezone.utc)
        return self.status
    
    @staticmethod
    def _mix_arcade_to_pwm(left_speed: float, right_speed: float) -> tuple[int, int]:
        """Convert differential wheel speeds into steer/throttle PWM microseconds."""
        max_input = max(1.0, abs(left_speed), abs(right_speed))
        left_norm = left_speed / max_input
        right_norm = right_speed / max_input

        linear = (left_norm + right_norm) / 2.0
        angular = (right_norm - left_norm) / 2.0

        throttle_us = RoboHATService._scale_to_pwm(linear)
        steer_us = RoboHATService._scale_to_pwm(angular, span=350)
        return steer_us, throttle_us

    @staticmethod
    def _scale_to_pwm(value: float, span: int = 450, center: int = 1500) -> int:
        value = max(-1.0, min(1.0, value))
        us = int(round(center + value * span))
        return max(1000, min(2000, us))

    async def shutdown(self):
        """Shutdown RoboHAT service"""
        logger.info("Shutting down RoboHAT service")
        
        self.running = False

        # Try to hand control back to RC so that the mower is safe even if the
        # backend stops responding.
        try:
            await self._set_rc_enabled(True)
        except Exception:
            pass
        
        # Cancel background tasks
        if self.watchdog_task:
            self.watchdog_task.cancel()
            try:
                await self.watchdog_task
            except asyncio.CancelledError:
                pass
        
        if self.read_task:
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass
        
        # Close serial connection
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        
        self.status.serial_connected = False
        logger.info("RoboHAT service shutdown complete")


# Global RoboHAT service instance
robohat_service: Optional[RoboHATService] = None


def get_robohat_service() -> Optional[RoboHATService]:
    """Get global RoboHAT service instance"""
    return robohat_service


async def initialize_robohat_service(serial_port: str = "/dev/ttyACM0", baud_rate: int = 115200) -> bool:
    """Initialize global RoboHAT service"""
    global robohat_service
    
    if robohat_service is None:
        robohat_service = RoboHATService(serial_port, baud_rate)
    
    return await robohat_service.initialize()


async def shutdown_robohat_service():
    """Shutdown global RoboHAT service"""
    global robohat_service
    
    if robohat_service:
        await robohat_service.shutdown()
        robohat_service = None
