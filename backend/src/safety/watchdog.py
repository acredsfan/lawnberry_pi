from __future__ import annotations

"""Software watchdog (T031).

Async loop monitors time since last heartbeat; triggers E-stop if exceeded.
"""

import asyncio
import time
from typing import Optional

from .estop_handler import EstopHandler


class Watchdog:
    def __init__(self, estop: EstopHandler, timeout_ms: int) -> None:
        self._estop = estop
        self._timeout_ms = max(1, int(timeout_ms))
        self._last_heartbeat = time.perf_counter()
        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()

    def heartbeat(self) -> None:
        self._last_heartbeat = time.perf_counter()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_evt.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        try:
            while not self._stop_evt.is_set():
                await asyncio.sleep(0.01)
                elapsed_ms = (time.perf_counter() - self._last_heartbeat) * 1000.0
                if elapsed_ms > self._timeout_ms:
                    self._estop.trigger_estop("watchdog_timeout")
                    # After triggering, prevent repeated triggers and exit
                    break
        finally:
            pass
