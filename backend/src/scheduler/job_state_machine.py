from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from backend.src.models.scheduled_job import JobState, ScheduledJob


_ALLOWED: Final[dict[JobState, set[JobState]]] = {
    JobState.IDLE: {JobState.SCHEDULED},
    JobState.SCHEDULED: {JobState.RUNNING, JobState.FAILED},
    JobState.RUNNING: {JobState.PAUSED, JobState.COMPLETED, JobState.FAILED},
    JobState.PAUSED: {JobState.RUNNING, JobState.FAILED},
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
}


@dataclass
class TransitionResult:
    ok: bool
    reason: str | None = None


class JobStateMachine:
    def __init__(self, job: ScheduledJob):
        self._job = job

    @property
    def job(self) -> ScheduledJob:
        return self._job

    def _as_state(self, value: JobState | str) -> JobState:
        # Pydantic may materialize enum values as strings due to Config.use_enum_values
        return value if isinstance(value, JobState) else JobState(value)

    def _state_name(self, value: JobState | str) -> str:
        return value.value if isinstance(value, JobState) else str(value)

    def _ensure(self, target: JobState) -> None:
        cur_raw = self._job.state
        cur = self._as_state(cur_raw)
        if target not in _ALLOWED.get(cur, set()):
            raise ValueError(f"Invalid transition: {self._state_name(cur)} -> {self._state_name(target)}")

    def schedule(self) -> None:
        self._ensure(JobState.SCHEDULED)
        self._job.state = JobState.SCHEDULED

    def start(self) -> None:
        self._ensure(JobState.RUNNING)
        self._job.state = JobState.RUNNING
        # capture last_run_time_us when entering RUNNING
        import time
        self._job.last_run_time_us = int(time.time() * 1_000_000)

    def pause(self) -> None:
        self._ensure(JobState.PAUSED)
        self._job.state = JobState.PAUSED

    def resume(self) -> None:
        self._ensure(JobState.RUNNING)
        self._job.state = JobState.RUNNING

    def complete(self) -> None:
        self._ensure(JobState.COMPLETED)
        self._job.state = JobState.COMPLETED

    def fail(self, reason: str | None = None) -> None:
        # Allow failure from any non-terminal state for robustness
        current = self._as_state(self._job.state)
        if current in (JobState.COMPLETED, JobState.FAILED):
            raise ValueError(
                f"Invalid transition: {self._state_name(current)} -> {self._state_name(JobState.FAILED)}"
            )
        self._job.state = JobState.FAILED
        self._job.error_message = reason
