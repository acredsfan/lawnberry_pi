from __future__ import annotations

"""Software watchdog (T031).

Thread-based monitor of client heartbeats; triggers E-stop if exceeded to avoid
async loop starvation.
"""

import asyncio
import logging
import threading
import time

from .estop_handler import EstopHandler

logger = logging.getLogger(__name__)


class Watchdog:
    def __init__(self, estop: EstopHandler, timeout_ms: int) -> None:
        self._estop = estop
        self._timeout_ms = max(1, int(timeout_ms))
        self._timeout_s = self._timeout_ms / 1000.0
        self._last_heartbeat = time.perf_counter()
        self._armed_reasons: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

    def heartbeat(self) -> None:
        with self._lock:
            self._last_heartbeat = time.perf_counter()

    def arm(self, reason: str = "motion") -> None:
        """Arm timeout enforcement while a hazardous actuator is active."""
        with self._lock:
            self._armed_reasons.add(reason)
            self._last_heartbeat = time.perf_counter()

    def disarm(self, reason: str | None = None) -> None:
        """Disarm one actuator source, or all sources when reason is omitted."""
        with self._lock:
            if reason is None:
                self._armed_reasons.clear()
            else:
                self._armed_reasons.discard(reason)
            self._last_heartbeat = time.perf_counter()

    @property
    def armed(self) -> bool:
        with self._lock:
            return bool(self._armed_reasons)

    async def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop_evt.clear()
            with self._lock:
                self._last_heartbeat = time.perf_counter()
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="LawnBerryWatchdog"
            )
            self._thread.start()
            logger.info(f"Threaded safety watchdog started (timeout={self._timeout_ms} ms)")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._thread:
            while self._thread.is_alive():
                await asyncio.sleep(0.01)
            self._thread = None
            logger.info("Threaded safety watchdog stopped")

    def _run(self) -> None:
        try:
            while not self._stop_evt.is_set():
                time.sleep(0.01)
                with self._lock:
                    armed = bool(self._armed_reasons)
                    elapsed_s = time.perf_counter() - self._last_heartbeat
                    reasons = ",".join(sorted(self._armed_reasons))
                if armed and elapsed_s > self._timeout_s:
                    logger.error(
                        "Watchdog timeout detected (elapsed=%.1fms, limit=%dms, armed=%s). "
                        "Triggering E-stop!",
                        elapsed_s * 1000.0,
                        self._timeout_ms,
                        reasons or "unknown",
                    )
                    self._estop.trigger_estop("watchdog_timeout")
                    with self._lock:
                        self._armed_reasons.clear()
                        self._last_heartbeat = time.perf_counter()
        except Exception as e:
            logger.exception(f"Exception in watchdog thread: {e}")
        finally:
            pass
