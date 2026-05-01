"""Text protocol bridge for the RoboHAT RP2040 control board.

The bundled CircuitPython firmware (`robohat-rp2040-code/code.py`) exposes a
human-readable command set on its USB serial interface.  Earlier iterations of
the backend spoke a JSON RPC dialect which the current firmware rejects, so the
communication layer has to emit the same text commands you would type over a
serial console (e.g. ``rc=disable``, ``pwm,1500,1600``).

This module keeps the async façade expected by the FastAPI endpoints while
performing the minimal blocking serial I/O in tiny, protected critical sections.
"""

import ast
import asyncio
import glob
import json
import logging
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import serial

try:  # Best-effort optional import for USB device enumeration.
    from serial.tools import list_ports  # type: ignore
except Exception:  # pragma: no cover - serial.tools may be unavailable in CI
    list_ports = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class RoboHATStatus:
    """RoboHAT firmware status"""

    firmware_version: str | None = None
    uptime_seconds: int = 0
    watchdog_active: bool = False
    last_watchdog_echo: str | None = None
    watchdog_latency_ms: float = 0.0
    serial_connected: bool = False
    error_count: int = 0
    last_error: str | None = None
    motor_controller_ok: bool = False
    encoder_feedback_ok: bool = False
    encoder_position: int = 0
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
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
            "encoder_position": self.encoder_position,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "health_status": self.get_health_status(),
        }

    def get_health_status(self) -> str:
        """Get overall health status"""
        if not self.serial_connected:
            return "disconnected"
        # Only fault on sustained errors – occasional race-condition rejections
        # (firmware USB-timeout race) accumulate slowly and are not fatal.
        if self.error_count > 50:
            return "fault"
        if not self.watchdog_active or not self.motor_controller_ok:
            return "warning"
        return "healthy"


class RoboHATService:
    """RoboHAT RP2040 serial bridge service"""

    _PROBE_STARTUP_SETTLE_SECONDS = 3.0  # USB CDC resets on open; wait for CircuitPython to boot
    _PROBE_UART_SETTLE_SECONDS = 0.3  # Hardware UART doesn't reset on open; brief drain only
    _RECONNECT_DELAY_SECONDS = 5.0
    _MAX_RECONNECT_ATTEMPTS = 12  # ~1 minute of retries

    # Hardware UART port patterns — opening these does NOT trigger a CircuitPython reset,
    # so the long USB CDC settle delay is not needed.
    _UART_PORT_PATTERNS = ("ttyAMA", "ttyS", "serial0", "ttyMFD", "ttySC", "ttyO")

    def __init__(self, serial_port: str = "/dev/ttyACM0", baud_rate: int = 115200):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.serial_conn: serial.Serial | None = None
        self.status = RoboHATStatus()
        self.running = False
        self.watchdog_task: asyncio.Task | None = None
        self.read_task: asyncio.Task | None = None
        self._serial_lock = asyncio.Lock()
        self._rc_enabled = True
        self._usb_control_requested = False
        self._pending_rc_state: bool | None = None
        self._pending_rc_since: float = 0.0
        self._last_status_at: float = 0.0
        # Track the last time we SENT any command to the firmware.  The firmware
        # USB timeout (SERIAL_TIMEOUT ≈ 5 s) is reset by received commands, not
        # by messages it sends us.  Using _last_status_at (incoming) for the
        # keepalive gate was the root-cause of the "firmware USB timeout while
        # we think we're in USB mode" bug — status heartbeats kept _last_status_at
        # fresh while no actual commands reached the firmware.
        self._last_cmd_sent_at: float = 0.0
        # Track last PWM sent so we can refresh it to avoid firmware USB timeout
        self._last_pwm: tuple[int, int] = (1500, 1500)
        self._last_pwm_at: float = 0.0
        # Set True when emergency_stop() is called while serial is unavailable;
        # cleared once neutral PWM is delivered after reconnect.
        self._estop_pending: bool = False
        # Counter incremented each time the firmware acks a PWM command.  Using a
        # counter avoids the race where a [STATUS] message overwrites
        # last_watchdog_echo between the PWM send and the ack-poll iteration.
        self._pwm_ack_count: int = 0
        # Event set by _process_line when a PWM ack arrives; cleared in
        # send_motor_command before each new command so _wait_for_pwm_ack can
        # await notification instead of polling at a fixed 20 ms interval.
        self._pwm_ack_event: asyncio.Event = asyncio.Event()
        # Reconnect coordination — prevents concurrent reconnect tasks and enables
        # periodic retry after the initial attempt window is exhausted.
        self._reconnecting: bool = False
        self._last_reconnect_attempt: float = 0.0
        # Encoder enabled flag — False when hall sensors are missing/unreliable.
        # Loaded from config/hardware.yaml encoders.enabled (default True).
        self._encoder_enabled: bool = True
        try:
            from backend.src.core.config_loader import get_config_loader

            hw, _ = get_config_loader().get()
            self._encoder_enabled = bool(getattr(hw, "encoder_enabled", True))
            if not self._encoder_enabled:
                logger.info(
                    "Encoder feedback disabled via hardware config (encoders.enabled: false)"
                )
        except Exception:
            pass  # non-fatal; fall back to enabled (safe default)

    @staticmethod
    def _is_robohat_response_line(line: str) -> bool:
        """Return True when a serial line looks like the RoboHAT firmware."""
        text = (line or "").strip().lower()
        if not text:
            return False
        return (
            text.startswith("[usb]")
            or text.startswith("[uart]")
            or text.startswith("[serial]")
            or text.startswith("[rc-")
            or text.startswith("[status]")
            or text.startswith("[rc]")
            or text.startswith("▶")
            or text.startswith("\u25b6")
            or "robohat" in text
        )

    def _is_uart_port(self, port: str) -> bool:
        """Return True when the port path looks like a hardware UART (not USB CDC)."""
        return any(p in port for p in self._UART_PORT_PATTERNS)

    async def _probe_firmware_response(self, timeout: float = 2.5) -> bool:
        """Verify the opened serial port actually speaks the RoboHAT protocol."""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False

        saw_robohat_line = False

        # USB CDC ports trigger a CircuitPython reset when opened — wait for the
        # firmware to reach its main loop before sending commands.
        # Hardware UART ports do NOT trigger a reset; a short drain window is enough.
        port_name = str(getattr(self.serial_conn, "name", None) or self.serial_port or "")
        settle_seconds = (
            self._PROBE_UART_SETTLE_SECONDS
            if self._is_uart_port(port_name)
            else self._PROBE_STARTUP_SETTLE_SECONDS
        )
        settle_deadline = time.monotonic() + settle_seconds
        while time.monotonic() < settle_deadline:
            try:
                if self.serial_conn.in_waiting:
                    raw = await asyncio.to_thread(self.serial_conn.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        await asyncio.sleep(0.05)
                        continue
                    self._process_line(line)
                    if self._is_robohat_response_line(line):
                        saw_robohat_line = True
                else:
                    await asyncio.sleep(0.05)
            except Exception:
                await asyncio.sleep(0.05)

        try:
            await self._send_line("rc=disable")
        except Exception:
            return False

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.serial_conn.in_waiting:
                    raw = await asyncio.to_thread(self.serial_conn.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        await asyncio.sleep(0.05)
                        continue
                    self._process_line(line)
                    if self._is_robohat_response_line(line):
                        saw_robohat_line = True
                        return True
                else:
                    await asyncio.sleep(0.05)
            except Exception:
                await asyncio.sleep(0.05)

        if saw_robohat_line:
            self.status.last_error = None
            return True

        self.status.last_error = "robohat_unresponsive"
        return False

    async def initialize(self) -> bool:
        """Initialize RoboHAT serial connection"""
        try:
            logger.info(
                f"Initializing RoboHAT service on {self.serial_port} at {self.baud_rate} baud"
            )

            # Open serial connection
            self.serial_conn = serial.Serial(
                port=self.serial_port, baudrate=self.baud_rate, timeout=1.0, write_timeout=1.0
            )

            # Wait for connection to stabilize.
            # USB CDC ports cause CircuitPython to reset; UART ports do not.
            settle = (
                self._PROBE_UART_SETTLE_SECONDS
                if self._is_uart_port(self.serial_port)
                else self._PROBE_STARTUP_SETTLE_SECONDS
            )
            await asyncio.sleep(settle)

            # Flush any banner/boot messages so we begin with a clean buffer
            self._drain_serial_buffer()

            if not await self._probe_firmware_response():
                logger.warning(
                    "Serial device %s did not respond like RoboHAT firmware", self.serial_port
                )
                try:
                    self.serial_conn.close()
                finally:
                    self.serial_conn = None
                self.status.serial_connected = False
                return False

            self.status.serial_connected = True
            self.running = True
            await self._apply_estop_if_pending()  # honour any e-stop received while disconnected

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
            self._last_cmd_sent_at = time.monotonic()
            return True
        except Exception as exc:  # pragma: no cover - hardware error path
            logger.error("Failed to send RoboHAT command line '%s': %s", line, exc)
            self.status.error_count += 1
            self.status.last_error = str(exc)
            return False

    async def _wait_for_pwm_ack(
        self, *, timeout: float = 1.0, _baseline: int | None = None
    ) -> bool:
        """Wait for the firmware to acknowledge or reject the last PWM command.

        Uses asyncio.Event notification (set by _process_line on ack) instead of
        fixed-interval polling so response latency equals the actual serial round-trip
        rather than the poll interval.  _baseline should be the _pwm_ack_count value
        captured (in send_motor_command) AFTER clearing the event and BEFORE sending
        the command, so stale acks from previous commands are not counted.
        """
        deadline = time.monotonic() + timeout
        starting_errors = self.status.error_count
        starting_count = self._pwm_ack_count if _baseline is None else _baseline

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            last_error = (self.status.last_error or "").lower()
            if self.status.error_count > starting_errors and "pwm" in last_error:
                return False
            if self._pwm_ack_count > starting_count:
                return True
            # Clear then re-check to close the TOCTOU window before waiting.
            self._pwm_ack_event.clear()
            if self._pwm_ack_count > starting_count:
                return True
            try:
                await asyncio.wait_for(self._pwm_ack_event.wait(), timeout=min(remaining, 0.5))
            except TimeoutError:
                pass

        self.status.last_error = self.status.last_error or "pwm_ack_timeout"
        logger.warning("Timed out waiting for RoboHAT PWM acknowledgement")
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
            if (
                self._pending_rc_state is False
                and (time.monotonic() - self._pending_rc_since) > 1.0
            ):
                logger.warning(
                    "RoboHAT RC disable acknowledgement still pending while RC remains active; retrying command"
                )
                await self._set_rc_enabled(False, force=True)
                return
            await self._set_rc_enabled(False)
            return

        if self._pending_rc_state is not None:
            if (time.monotonic() - self._pending_rc_since) > 1.0:
                logger.warning("RoboHAT RC disable acknowledgement still pending; retrying command")
                await self._set_rc_enabled(False, force=True)
            return
        # Refresh the last commanded PWM periodically to prevent the firmware
        # from timing out back to RC mode (SERIAL_TIMEOUT ≈ 5s on firmware).
        # NOTE: use _last_cmd_sent_at (when WE sent a command) not _last_status_at
        # (when the firmware sent us a message) — the firmware timeout clock is
        # reset by commands received, not by messages it emits.
        now = time.monotonic()
        if (now - self._last_cmd_sent_at) >= 0.9:
            steer_us, thr_us = self._last_pwm
            await self._send_line(f"pwm,{steer_us},{thr_us}")
            self._last_pwm_at = now

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

    async def _send_safe_state_on_reconnect(self) -> None:
        """Send neutral PWM and blade-off immediately after a successful reconnect.

        This ensures the firmware is in a known-safe state before the backend
        starts issuing navigation commands, regardless of what the firmware may
        have been commanded before the disconnect.
        """
        try:
            await self._send_line("pwm,1500,1500")
            self._last_pwm = (1500, 1500)
            self._last_pwm_at = time.monotonic()
            await asyncio.sleep(0.05)
            await self._send_line("blade=off")
            logger.info("RoboHAT safe state applied after reconnect")
        except Exception as exc:
            logger.warning("Failed to apply safe state after RoboHAT reconnect: %s", exc)

    async def _reconnect(self) -> None:
        """Attempt to re-open the serial connection after a disconnect.

        Probes all known candidate ports (stable by-id path first) so a
        device renumbering (e.g. ttyACM0 → ttyACM2 after USB replug) is
        handled transparently without a backend restart.

        Uses self._reconnecting as a guard so only one reconnect task runs at a
        time.  self._last_reconnect_attempt is updated in the finally block so
        _read_loop can schedule the next attempt after a back-off interval.
        """
        if self._reconnecting:
            return
        self._reconnecting = True
        try:
            self.status.serial_connected = False
            if self.serial_conn:
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None

            for attempt in range(self._MAX_RECONNECT_ATTEMPTS):
                if not self.running:
                    return
                await asyncio.sleep(self._RECONNECT_DELAY_SECONDS)
                candidates = _candidate_serial_ports()
                for candidate in candidates:
                    if not self.running:
                        return
                    logger.info(
                        "RoboHAT reconnect attempt %d/%d on %s",
                        attempt + 1,
                        self._MAX_RECONNECT_ATTEMPTS,
                        candidate,
                    )
                    try:
                        conn = serial.Serial(
                            port=candidate,
                            baudrate=self.baud_rate,
                            timeout=1.0,
                            write_timeout=1.0,
                        )
                        self.serial_conn = conn
                        self.serial_port = candidate
                        settle = (
                            self._PROBE_UART_SETTLE_SECONDS
                            if self._is_uart_port(candidate)
                            else self._PROBE_STARTUP_SETTLE_SECONDS
                        )
                        await asyncio.sleep(settle)
                        self._drain_serial_buffer()
                        if await self._probe_firmware_response():
                            # Send safe state BEFORE marking connected so the navigation
                            # grace loop cannot see serial_connected=True and race with
                            # the safe-state commands.
                            await self._send_safe_state_on_reconnect()
                            await self._apply_estop_if_pending()
                            self.status.serial_connected = True
                            # Start watchdog if it was never started (first-connect path
                            # from a delayed-boot reconnect) or if it died.
                            if self.watchdog_task is None or self.watchdog_task.done():
                                self.watchdog_task = asyncio.create_task(self._watchdog_loop())
                            logger.info("RoboHAT reconnected on %s", candidate)
                            return
                        conn.close()
                        self.serial_conn = None
                    except Exception as exc:
                        logger.debug("RoboHAT reconnect candidate %s failed: %s", candidate, exc)
                        self.serial_conn = None

            logger.error("RoboHAT reconnect exhausted all attempts; serial remains offline")
        finally:
            self._reconnecting = False
            self._last_reconnect_attempt = time.monotonic()

    async def _read_loop(self):
        """Continuous read loop for RoboHAT messages, with USB replug recovery.

        Reconnect scheduling is centralised here using self._reconnecting and
        self._last_reconnect_attempt so there is exactly one code path that
        starts a reconnect task.  When _reconnect() exhausts its initial
        attempts it sets self._reconnecting = False and updates
        self._last_reconnect_attempt; this loop then retries every
        _IDLE_RECONNECT_INTERVAL seconds until the service stops.
        """
        _IDLE_RECONNECT_INTERVAL = 60.0
        while self.running:
            try:
                # Drain ALL lines in the serial buffer before sleeping so that
                # a preceding command response (e.g. blade=off → "[USB] Blade: OFF")
                # does not block the PWM ack from being processed within the same
                # 20 ms window.  Each asyncio.to_thread() still yields to the event
                # loop, so other coroutines remain responsive during the drain.
                while self.serial_conn and self.serial_conn.is_open and self.serial_conn.in_waiting:
                    raw = await asyncio.to_thread(self.serial_conn.readline)
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if line:
                        self._process_line(line)

                # Periodic retry after initial reconnect attempts are exhausted.
                # This is the only place that starts a reconnect task so we
                # never have two competing reconnect coroutines running.
                if (
                    not self.status.serial_connected
                    and not self._reconnecting
                    and time.monotonic() - self._last_reconnect_attempt >= _IDLE_RECONNECT_INTERVAL
                ):
                    logger.info(
                        "RoboHAT still disconnected after %.0fs; scheduling reconnect",
                        _IDLE_RECONNECT_INTERVAL,
                    )
                    asyncio.create_task(self._reconnect())

                await asyncio.sleep(0.005)  # 5 ms — lower floor for ack detection

            except asyncio.CancelledError:
                break
            except (serial.SerialException, OSError) as e:
                if not self._reconnecting:
                    logger.warning("RoboHAT serial connection lost (%s); attempting reconnect", e)
                    asyncio.create_task(self._reconnect())
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"Read loop error: {e}")
                await asyncio.sleep(0.1)

    @staticmethod
    def _parse_encoder_from_line(line: str) -> int | None:
        """Extract encoder tick count from a firmware heartbeat/status line.

        Matches ``enc=N`` or ``"encoder": N`` patterns in lines such as::

            [USB] signal=LOST steer=1500 µs thr=1500 µs blade=OFF enc=42
            [RC-emergency] ... enc=-17
        """
        m = re.search(r"\benc=(-?\d+)", line)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        return None

    _VERSION_RE = re.compile(r"firmware[:\s]+v?(\d+\.\d+[\.\d]*)", re.I)

    def _try_parse_firmware_version(self, line: str) -> None:
        m = self._VERSION_RE.search(line)
        if m:
            self.status.firmware_version = m.group(1)
            logger.info("RoboHAT firmware version: %s", self.status.firmware_version)

    def _process_line(self, line: str) -> None:
        """Parse human-readable firmware messages and update status fields."""
        self._try_parse_firmware_version(line)
        if not line:
            return

        line_lower = line.lower()

        if line_lower.startswith("[status]"):
            try:
                brace_index = line.index("{")
                raw_payload = line[brace_index:]
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    payload = ast.literal_eval(raw_payload)
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
            enc = payload.get("encoder")
            if self._encoder_enabled:
                self.status.encoder_feedback_ok = enc is not None
                if enc is not None:
                    self.status.encoder_position = int(enc)
            else:
                self.status.encoder_feedback_ok = False
            self.status.last_watchdog_echo = "status"
            if not rc_enabled:
                self.status.last_error = None
            return

        if (
            "rc enabled" in line_lower
            or "back to rc" in line_lower
            or "timeout" in line_lower
            and "rc mode" in line_lower
        ):
            self._mark_rc_state(True)
            self._last_status_at = time.monotonic()
            logger.info("RoboHAT reported RC mode active")
            return

        if "rc disabled" in line_lower:
            self._mark_rc_state(False)
            self._last_status_at = time.monotonic()
            self.status.motor_controller_ok = True
            self.status.last_watchdog_echo = "rc_disable_ack"
            self.status.last_error = None
            # Clear accumulated transient errors – USB control is confirmed healthy.
            self.status.error_count = 0
            logger.info("RoboHAT reported USB control active")
            return

        if line_lower.startswith("[usb] pwm"):
            self._last_status_at = time.monotonic()
            self._pwm_ack_count += 1
            self._pwm_ack_event.set()
            self.status.motor_controller_ok = True
            self.status.last_watchdog_echo = "pwm_ack"
            self.status.last_error = None
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

        if line_lower.startswith("[usb]"):
            self._last_status_at = time.monotonic()
            self.status.motor_controller_ok = not self._rc_enabled
            self.status.last_watchdog_echo = line.strip()
            if not self._rc_enabled:
                self.status.last_error = None
            # Parse encoder tick count from firmware heartbeat lines, e.g.:
            # "[USB] signal=LOST steer=1500 µs thr=1500 µs blade=OFF enc=42"
            enc = self._parse_encoder_from_line(line)
            if enc is not None and self._encoder_enabled:
                self.status.encoder_position = enc
                self.status.encoder_feedback_ok = True
            return

        if line_lower.startswith("\u25b6") or line_lower.startswith("▶"):
            # Firmware banner – parse version string if present.
            self._try_parse_firmware_version(line)
            return

        if line_lower.startswith("[rc]") or line_lower.startswith("[rc-"):
            # Heartbeat from firmware – keep as last echo and parse encoder.
            self.status.last_watchdog_echo = line
            self._last_status_at = time.monotonic()
            enc = self._parse_encoder_from_line(line)
            if enc is not None and self._encoder_enabled:
                self.status.encoder_position = enc
                self.status.encoder_feedback_ok = True
            return

        # For everything else, keep a debug breadcrumb without polluting logs.
        logger.debug("RoboHAT: %s", line)

    async def send_motor_command(
        self, left_speed: float, right_speed: float, ack_timeout: float = 0.35
    ) -> bool:
        """Send motor command to RoboHAT"""
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        if self._estop_pending:
            logger.warning("Motor command refused: emergency stop pending")
            return False

        if not await self._ensure_usb_control(timeout=0.9, retries=2):
            return False

        steer_us, throttle_us = self._mix_arcade_to_pwm(left_speed, right_speed)
        # Clear ack event and capture baseline BEFORE sending so _wait_for_pwm_ack
        # only counts acks that arrive in response to this specific command.
        self._pwm_ack_event.clear()
        _ack_baseline = self._pwm_ack_count
        ok = await self._send_line(f"pwm,{steer_us},{throttle_us}")
        if ok:
            ok = await self._wait_for_pwm_ack(timeout=ack_timeout, _baseline=_ack_baseline)

        if ok:
            self.status.motor_controller_ok = True
            self.status.last_watchdog_echo = f"pwm:{steer_us}/{throttle_us}"
            self.status.last_error = None
            # Record last PWM so watchdog can refresh the same command and
            # prevent firmware USB timeout during longer manoeuvres.
            self._last_pwm = (steer_us, throttle_us)
            self._last_pwm_at = time.monotonic()
        else:
            self.status.motor_controller_ok = False
            self.status.last_error = self.status.last_error or "pwm_send_failed"
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
            self._estop_pending = True
            logger.critical("Serial not available; e-stop queued for next reconnect")
            return False

        usb_ready = await self._ensure_usb_control(timeout=0.6, retries=2)
        if not usb_ready:
            logger.critical("Emergency stop failed closed: USB control acknowledgement unavailable")
            self._estop_pending = True
            self._last_pwm = (1500, 1500)
            self._last_pwm_at = time.monotonic()
            self.status.motor_controller_ok = False
            self.status.last_error = self.status.last_error or "usb_control_unavailable"
            return False
        ok = await self._send_line("pwm,1500,1500")
        # Record neutral PWM as last command to maintain safe stop if needed
        self._last_pwm = (1500, 1500)
        self._last_pwm_at = time.monotonic()
        ok = await self._send_line("blade=off") and ok
        self.status.motor_controller_ok = False
        self.status.last_watchdog_echo = "emergency_stop"
        if not ok:
            self.status.last_error = "emergency_stop_failed"
        else:
            self.status.last_error = None
        return ok

    async def clear_emergency(self) -> bool:
        """Clear emergency stop on RoboHAT"""
        logger.info("Clearing emergency stop on RoboHAT")
        if not self.serial_conn or not self.serial_conn.is_open or not self.running:
            return False

        if not await self._ensure_usb_control(timeout=0.9, retries=2):
            return False
        ok = await self._send_line("rc=disable")
        if ok:
            self._estop_pending = False
            self.status.last_error = None
        else:
            self.status.last_error = "clear_emergency_failed"
        return ok

    def get_status(self) -> RoboHATStatus:
        """Get current RoboHAT status"""
        self.status.timestamp = datetime.now(UTC)
        return self.status

    async def _apply_estop_if_pending(self) -> None:
        """Send queued emergency stop if one was requested while disconnected."""
        if not self._estop_pending:
            return
        logger.critical("Applying queued emergency stop after serial reconnect")
        await self._send_line("pwm,1500,1500")
        await self._send_line("blade=off")
        self._last_pwm = (1500, 1500)
        self._last_pwm_at = time.monotonic()
        self._estop_pending = False

    @staticmethod
    def _mix_arcade_to_pwm(left_speed: float, right_speed: float) -> tuple[int, int]:
        """Convert differential wheel speeds into steer/throttle PWM microseconds.

        Note: Navigation service sends left/right variables in swapped order
        (due to MDDRC10 motor driver physical wiring inversion). This arcade mix
        inverts the angular calculation to compensate.
        """
        max_input = max(1.0, abs(left_speed), abs(right_speed))
        left_norm = left_speed / max_input
        right_norm = right_speed / max_input

        linear = (left_norm + right_norm) / 2.0
        # INVERTED arcade formula to match navigation's swapped left/right semantics
        angular = (right_norm - left_norm) / 2.0

        throttle_us = RoboHATService._scale_to_pwm(linear)
        steer_us = RoboHATService._scale_to_pwm(angular, span=350)
        return steer_us, throttle_us

    @staticmethod
    def _scale_to_pwm(
        value: float, span: int = 450, center: int = 1500, dead_zone: int = 80
    ) -> int:
        """Convert a [-1, 1] value to PWM microseconds.

        ``dead_zone`` is the minimum µs offset from *center* that the motor
        driver requires before the motors actually move (MDDRC10 dead band).
        When ``value`` is non-zero the output is shifted past the dead zone so
        that even small commands produce real wheel motion.
        """
        value = max(-1.0, min(1.0, value))
        if abs(value) < 1e-4:
            return center
        sign = 1 if value > 0 else -1
        # Map [0..1] → [dead_zone .. span] µs offset
        live_span = span - dead_zone
        us = int(round(center + sign * (dead_zone + abs(value) * live_span)))
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
robohat_service: RoboHATService | None = None


def get_robohat_service() -> RoboHATService | None:
    """Get global RoboHAT service instance"""
    return robohat_service


_ROBOHAT_PORT_ENV_VARS: tuple[str, ...] = (
    "ROBOHAT_SERIAL_PORT",
    "ROBOHAT_PORT",
    "LAWN_ROBOHAT_PORT",
)
_ROBOHAT_KEYWORDS: tuple[str, ...] = (
    "robohat",
    "rp2040",
    "circuitpython",
    "cytron",
    "lawnberry",
)
_RP2040_VENDOR_IDS: set[int] = {0x2E8A}  # Raspberry Pi RP2040 VID


def _settings_profile_paths() -> Iterable[Path]:
    """Candidate settings profile files that may contain RoboHAT overrides."""

    env_dir = os.getenv("LAWN_SETTINGS_DIR") or os.getenv("LAWN_CONFIG_DIR")
    if env_dir:
        base = Path(env_dir)
        yield base / "default.json"
        yield base / "settings.json"

    system_base = Path("./config")
    yield system_base / "default.json"
    yield system_base / "settings.json"

    project_base = Path(os.getcwd()) / "config"
    yield project_base / "default.json"
    yield project_base / "settings.json"


def _read_profile_robohat_port() -> str | None:
    """Extract RoboHAT serial port override from persisted settings if present."""

    for path in _settings_profile_paths():
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            hardware = data.get("hardware") if isinstance(data, dict) else None
            port = hardware.get("robohat_port") if isinstance(hardware, dict) else None
            if isinstance(port, str) and port.strip():
                return port.strip()
        except Exception:  # pragma: no cover - permissive best-effort parsing
            continue
    return None


def _serial_by_id_candidates() -> list[str]:
    patterns = (
        "/dev/serial/by-id/*RoboHAT*",
        "/dev/serial/by-id/*Robo_HAT*",
        "/dev/serial/by-id/*RP2040*",
        "/dev/serial/by-id/*CircuitPython*",
        "/dev/serial/by-id/*Pico*",
    )
    candidates: list[str] = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            if os.path.exists(path):
                candidates.append(path)
    return candidates


def _list_ports_candidates() -> list[str]:
    """Return serial devices that resemble the RoboHAT firmware."""

    if list_ports is None:  # pragma: no cover - serial.tools optional in CI
        return []

    matches: list[str] = []
    try:
        for info in list_ports.comports():  # type: ignore[attr-defined]
            desc_parts = [
                getattr(info, "device", ""),
                getattr(info, "description", ""),
                getattr(info, "manufacturer", ""),
                getattr(info, "product", ""),
            ]
            descriptor = " ".join(str(p or "") for p in desc_parts).lower()
            vid = getattr(info, "vid", None)
            if any(keyword in descriptor for keyword in _ROBOHAT_KEYWORDS):
                matches.append(info.device)
            elif isinstance(vid, int) and vid in _RP2040_VENDOR_IDS:
                matches.append(info.device)
    except Exception:  # pragma: no cover - enumeration issues should not abort startup
        return []
    return matches


def _known_excluded_devices() -> set[str]:
    """Return device paths that must never be probed as a RoboHAT port.

    Includes GPS receivers and the IMU UART (BNO085 on ttyAMA4 by default)
    so the scanner never wastes time on ports that will never respond as
    RoboHAT firmware, and never accidentally corrupts the IMU data stream.
    """
    excluded: set[str] = set()

    def _resolve_and_add(path: str) -> None:
        if not path:
            return
        try:
            real = os.path.realpath(path)
            if os.path.exists(real):
                excluded.add(real)
            excluded.add(path)
        except OSError:
            pass

    # GPS receivers
    for path in ["/dev/lawnberry-gps", "/dev/gps_rtk"]:
        _resolve_and_add(path)

    # IMU UART — resolve from env, hardware.yaml, then hardcoded default
    imu_port = os.getenv("BNO085_PORT", "")
    if not imu_port:
        try:
            import yaml

            hw_cfg_path = os.path.join(os.path.dirname(__file__), "../../../config/hardware.yaml")
            with open(os.path.realpath(hw_cfg_path)) as f:
                hw = yaml.safe_load(f) or {}
            imu_port = (hw.get("imu") or {}).get("port", "")
        except Exception:
            pass
    _resolve_and_add(imu_port or "/dev/ttyAMA4")

    return excluded


def _read_hardware_yaml_robohat_port() -> str | None:
    """Read the optional motor_controller_port field from hardware.yaml.

    Returns None when the field is absent so auto-discovery proceeds normally.
    Allows operators to pin the RoboHAT to a specific UART or USB path without
    needing environment variables.
    """
    try:
        import yaml

        hw_cfg_path = os.path.join(os.path.dirname(__file__), "../../../config/hardware.yaml")
        with open(os.path.realpath(hw_cfg_path)) as f:
            hw = yaml.safe_load(f) or {}
        port = hw.get("motor_controller_port", "") or ""
        return port.strip() or None
    except Exception:
        return None


def _known_gps_devices() -> set[str]:
    """Backward-compatible alias; use _known_excluded_devices() for full exclusion."""
    return _known_excluded_devices()


def _candidate_serial_ports(explicit: str | None = None) -> list[str]:
    """Build an ordered list of serial ports to try for RoboHAT.

    Priority order:
      1. Explicit argument or ROBOHAT_PORT / LAWN_ROBOHAT_PORT env vars
      2. motor_controller_port from hardware.yaml
      3. Stable udev symlink /dev/robohat (USB, by serial number)
      4. /dev/serial/by-id RP2040/CircuitPython entries (USB, stable)
      5. /dev/serial0 → ttyAMA0 (GPIO UART header — RoboHAT GPIO connection)
      6. Additional ttyAMA* UART ports (excluding the IMU on ttyAMA4)
      7. list_ports descriptors matching RoboHAT/RP2040 keywords
      8. ttyACM* and ttyUSB* (USB CDC, last resort)
      9. Historic default /dev/ttyACM0

    GPS and IMU ports are always excluded to avoid wasting probe time or
    corrupting other devices' data streams.
    """

    seen: set[str] = set()
    ordered: list[str] = []
    excluded_devices = _known_excluded_devices()

    def add(port: str | None, *, require_exists: bool = False) -> None:
        if port is None:
            return
        value = str(port).strip()
        if not value or value in seen:
            return
        if require_exists and value.startswith("/dev/") and not os.path.exists(value):
            return
        # Never probe GPS, IMU, or other known non-RoboHAT devices.
        if value in excluded_devices or os.path.realpath(value) in excluded_devices:
            return
        seen.add(value)
        # Also register the resolved path so symlinks (e.g. /dev/serial0 →
        # ttyAMA0) don't get probed a second time as the underlying device.
        try:
            real = os.path.realpath(value)
            if real != value:
                seen.add(real)
        except OSError:
            pass
        ordered.append(value)

    add(explicit)

    for env_var in _ROBOHAT_PORT_ENV_VARS:
        add(os.getenv(env_var))

    add(_read_profile_robohat_port())

    # Explicit hardware.yaml config beats all autodiscovery
    add(_read_hardware_yaml_robohat_port())

    # Stable udev symlink created by 99-robohat-rp2040.rules — always try first.
    add("/dev/robohat", require_exists=True)

    for path in _serial_by_id_candidates():
        add(path, require_exists=True)

    # UART candidates: /dev/serial0 is the primary GPIO UART (→ ttyAMA0).
    # The RoboHAT connects via the GPIO header over this UART in addition to USB.
    # ttyAMA4 (IMU) is already in excluded_devices and will be silently skipped.
    add("/dev/serial0", require_exists=True)
    for path in sorted(glob.glob("/dev/ttyAMA[0-9]*")):
        add(path, require_exists=True)

    for path in _list_ports_candidates():
        add(path, require_exists=True)

    for path in sorted(glob.glob("/dev/ttyACM*")):
        add(path, require_exists=True)
    for path in sorted(glob.glob("/dev/ttyUSB*")):
        add(path, require_exists=True)

    # Always include the historic default as a last resort.
    add("/dev/ttyACM0")

    return ordered


async def initialize_robohat_service(
    serial_port: str | None = None, baud_rate: int = 115200
) -> bool:
    """Initialize global RoboHAT service, probing common serial ports when needed."""
    global robohat_service

    if (
        robohat_service
        and robohat_service.running
        and robohat_service.status.serial_connected
        and (serial_port is None or robohat_service.serial_port == serial_port)
    ):
        return True

    if robohat_service and robohat_service.running:
        try:
            await robohat_service.shutdown()
        except Exception:  # pragma: no cover - shutdown best-effort
            pass
        robohat_service = None

    candidates = _candidate_serial_ports(serial_port)
    if not candidates:
        candidates = [serial_port or "/dev/ttyACM0"]

    last_attempt: RoboHATService | None = None
    for candidate in candidates:
        svc = RoboHATService(candidate, baud_rate)
        ok = await svc.initialize()
        last_attempt = svc
        if ok:
            robohat_service = svc
            logger.info("RoboHAT service initialized on %s", candidate)
            return True
        logger.warning(
            "RoboHAT initialization failed on %s: %s",
            candidate,
            svc.status.last_error or "unknown_error",
        )

    # All candidates failed.  Still register the last service instance and
    # start its read/reconnect loop so it can recover automatically when the
    # device appears (e.g. USB enumeration delayed at boot).
    robohat_service = last_attempt
    if robohat_service is not None:
        robohat_service.running = True
        robohat_service.read_task = asyncio.create_task(robohat_service._read_loop())
        logger.warning(
            "Unable to initialize RoboHAT service on any of [%s]; "
            "background reconnect loop started — will retry every 60 s",
            ", ".join(candidates),
        )
    else:
        logger.error("Unable to initialize RoboHAT service; no candidates to try")
    return False


async def shutdown_robohat_service():
    """Shutdown global RoboHAT service"""
    global robohat_service

    if robohat_service:
        await robohat_service.shutdown()
        robohat_service = None
