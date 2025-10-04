from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Dict, Optional

from backend.src.models.scheduled_job import ScheduledJob


Callback = Callable[[str], Awaitable[None]]


@dataclass
class _EverySpec:
    seconds: float


def _parse_every(schedule: str) -> Optional[_EverySpec]:
    # Supports forms: "@every 1s", "@every 500ms"
    m = re.match(r"^@every\s+(\d+)(ms|s)$", schedule.strip())
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2)
    if unit == "ms":
        return _EverySpec(seconds=value / 1000.0)
    return _EverySpec(seconds=float(value))


def _cron_matches_now_6field(expr: str, now: datetime) -> bool:
    """Very small 6-field cron matcher (sec min hour dom mon dow) with */n support.
    This is intentionally minimal for tests. Only handles '*', '*/n', or exact numbers.
    """
    parts = expr.strip().split()
    if len(parts) != 6:
        return False
    sec, minute, hour, dom, mon, dow = parts

    def match(part: str, value: int) -> bool:
        if part == "*":
            return True
        if part.startswith("*/"):
            try:
                n = int(part[2:])
                return (value % n) == 0
            except ValueError:
                return False
        # single int
        try:
            return int(part) == value
        except ValueError:
            return False

    return all(
        [
            match(sec, now.second),
            match(minute, now.minute),
            match(hour, now.hour),
            match(dom, now.day),
            match(mon, now.month),
            match(dow, now.weekday()),  # 0=Mon ... 6=Sun
        ]
    )


class JobScheduler:
    """Simple in-process scheduler with seconds-resolution cron and @every support.

    Designed to be ARM64-friendly and deterministic in tests. Not a full APScheduler.
    """

    def __init__(self, tick_interval: float = 0.5):
        self._jobs: Dict[str, tuple[ScheduledJob, Callback, Optional[_EverySpec], Optional[str]]] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = asyncio.Event()
        self._tick_interval = max(0.05, float(tick_interval))
        self._weather_suitable: Optional[Callable[[], bool]] = None

    async def add_job(self, name: str, schedule: str, callback: Callback) -> str:
        job_id = str(uuid.uuid4())
        job = ScheduledJob(job_id=job_id, name=name, cron_schedule=schedule)
        every_spec = _parse_every(schedule)
        # last_run_key used to gate @every cadence
        last_run_key = None
        self._jobs[job_id] = (job, callback, every_spec, last_run_key)
        return job_id

    async def start(self, weather_suitable: Optional[Callable[[], bool]] = None) -> None:
        if self._task and not self._task.done():
            return
        self._weather_suitable = weather_suitable
        self._running.set()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running.clear()
        t = self._task
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _run_loop(self) -> None:
        last_every_run: Dict[str, float] = {}
        try:
            while self._running.is_set():
                now = datetime.now()
                now_ts = time.time()
                to_run: list[tuple[str, ScheduledJob, Callback]] = []
                for job_id, (job, cb, every_spec, _) in self._jobs.items():
                    if every_spec is not None:
                        last_ts = last_every_run.get(job_id, 0.0)
                        if now_ts - last_ts >= every_spec.seconds:
                            last_every_run[job_id] = now_ts
                            to_run.append((job_id, job, cb))
                    else:
                        # Cron 6-field matching
                        if _cron_matches_now_6field(job.cron_schedule, now):
                            # Run at most once per second per job to avoid duplicates in same tick
                            key = f"{job_id}:{now.strftime('%Y-%m-%d %H:%M:%S')}"
                            # We can store last second per job in last_every_run dict as well
                            if last_every_run.get(key) is None:
                                last_every_run[key] = now_ts
                                to_run.append((job_id, job, cb))

                # Execute due jobs (respect weather gating if provided)
                for job_id, job, cb in to_run:
                    if self._weather_suitable is not None and not self._weather_suitable():
                        # Postpone: skip execution this tick
                        continue
                    job.last_run_time_us = int(now_ts * 1_000_000)
                    asyncio.create_task(cb(job_id))

                await asyncio.sleep(self._tick_interval)
        except asyncio.CancelledError:
            # Graceful shutdown
            raise
