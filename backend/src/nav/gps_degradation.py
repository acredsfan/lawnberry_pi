"""GPS Degradation Handler (T063)

Monitors GPS quality and triggers graceful degradation to MANUAL mode when:
- Reported accuracy exceeds 5 meters, or
- GPS signal appears lost for more than 10 seconds

This module is SIM_MODE-safe and only manipulates the in-memory RobotState.
It does not own any hardware resources. It should be started during app
startup and stopped during shutdown.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
from dataclasses import dataclass
from typing import Optional

from ..core.robot_state_manager import get_robot_state_manager
from ..models.robot_state import NavigationMode


@dataclass
class GPSDegradationConfig:
    max_accuracy_m: float = 5.0
    max_fix_age_s: float = 10.0
    check_interval_s: float = 1.0


class GPSDegradationMonitor:
    """Periodic monitor for GPS quality with mode fallback.

    If the robot is in AUTONOMOUS mode and GPS quality degrades beyond
    acceptable thresholds, switch to MANUAL mode. EMERGENCY_STOP transitions
    are handled elsewhere (e.g., geofence enforcer).
    """

    def __init__(self, config: Optional[GPSDegradationConfig] = None):
        self.cfg = config or GPSDegradationConfig()
        self._task: Optional[asyncio.Task] = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.cfg.check_interval_s * 2)
            except Exception:
                # Best-effort shutdown
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                self._tick()
            except Exception:
                # Do not crash on monitoring exceptions
                pass
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.cfg.check_interval_s)
            except asyncio.TimeoutError:
                continue

    def _tick(self) -> None:
        mgr = get_robot_state_manager()
        st = mgr.get_state()

        # Only enforce degradation during autonomous operation
        if st.navigation_mode != NavigationMode.AUTONOMOUS:
            return

        now = _dt.datetime.now(_dt.UTC)
        last = st.last_updated

        # Accuracy threshold
        accuracy = st.position.accuracy_m
        if accuracy is not None and accuracy > self.cfg.max_accuracy_m:
            st.navigation_mode = NavigationMode.MANUAL
            st.touch()
            return

        # Fix age threshold (if last state update older than limit)
        if last and (now - last).total_seconds() > self.cfg.max_fix_age_s:
            st.navigation_mode = NavigationMode.MANUAL
            st.touch()


__all__ = ["GPSDegradationMonitor", "GPSDegradationConfig"]
