import asyncio
import uuid
import zoneinfo
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from ..core.observability import observability
from ..core.state_manager import get_safety_state
from ..models.job import Job, JobPriority, JobProgress, JobStatus, JobType
from ..models.mission import Mission, MissionLifecycleStatus, MissionStatus

if TYPE_CHECKING:
    from .mission_service import MissionService
    from .websocket_hub import WebSocketHub

logger = observability.get_logger(__name__)


class _JobAdmissionBlocked(RuntimeError):
    """A job could not be admitted to the canonical mission path."""


_MISSION_JOB_TYPES = {JobType.SCHEDULED_MOW, JobType.MANUAL_MOW}


class JobsService:
    """Job scheduling and execution service."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.job_counter = 0
        self.scheduler_running = False
        self._scheduler_task: asyncio.Task | None = None
        self._running_tasks: set[asyncio.Task] = set()
        self._job_tasks: dict[str, asyncio.Task] = {}
        self._job_control_tasks: dict[str, asyncio.Task[bool]] = {}
        self._planning_occurrence_tasks: dict[str, asyncio.Task[None]] = {}
        self._mission_admission_lock = asyncio.Lock()
        self._mission_service: MissionService | None = None
        self._websocket_hub: WebSocketHub | None = None
        self._qualification_service: Any | None = None

    # ------------------------------------------------------------------
    # Dependency injection setters
    # ------------------------------------------------------------------

    def set_mission_service(self, mission_service: "MissionService") -> None:
        """Wire in MissionService (called from lifespan after both services are up)."""
        self._mission_service = mission_service

    def set_websocket_hub(self, websocket_hub: "WebSocketHub") -> None:
        """Wire in WebSocketHub for best-effort event broadcasting."""
        self._websocket_hub = websocket_hub

    def set_qualification_service(self, qualification_service: Any) -> None:
        """Wire in qualification evidence gate for scheduled blade-capable starts."""
        self._qualification_service = qualification_service

    def create_job(
        self,
        name: str,
        job_type: JobType = JobType.SCHEDULED_MOW,
        zones: list[str] = None,
        priority: JobPriority = JobPriority.NORMAL,
        **kwargs,
    ) -> Job:
        """Create a new job."""
        self.job_counter += 1
        job_id = f"job-{self.job_counter:04d}"

        job = Job(
            id=job_id, name=name, job_type=job_type, zones=zones or [], priority=priority, **kwargs
        )

        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Job | None:
        """Get job by ID."""
        return self.jobs.get(job_id)

    def list_jobs(
        self, status: JobStatus | None = None, job_type: JobType | None = None
    ) -> list[Job]:
        """List jobs with optional filtering."""
        jobs = list(self.jobs.values())

        if status:
            jobs = [job for job in jobs if job.status == status]

        if job_type:
            jobs = [job for job in jobs if job.job_type == job_type]

        # Sort by priority (high to low) then by created_at
        jobs.sort(key=lambda j: (-j.priority.value, j.created_at))
        return jobs

    def update_job(self, job_id: str, **updates) -> Job | None:
        """Update job properties."""
        job = self.jobs.get(job_id)
        if not job:
            return None

        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)

        return job

    def delete_job(self, job_id: str) -> bool:
        """Schedule deletion for legacy synchronous callers."""
        job = self.jobs.get(job_id)
        if job is None:
            return False
        if job.status == JobStatus.FAILED:
            # Failed mission-stop evidence must remain inspectable. The normal
            # retention cleanup can remove it after the diagnostic window.
            return False
        if job.status not in {JobStatus.RUNNING, JobStatus.PAUSED}:
            del self.jobs[job_id]
            return True
        if job.status in {JobStatus.RUNNING, JobStatus.PAUSED}:
            if job.mission_id and self._mission_service is None:
                return False
            if not job.mission_id and job_id not in self._job_tasks:
                return False
        return self._schedule_control_task(
            job_id,
            "delete",
            lambda: self.delete_job_async(job_id),
        )

    async def delete_job_async(self, job_id: str) -> bool:
        """Delete a job after confirming any active mission is safely stopped."""
        job = self.jobs.get(job_id)
        if job is None:
            return False
        if job.status == JobStatus.FAILED:
            return False
        if job.status in (JobStatus.RUNNING, JobStatus.PAUSED):
            await self.cancel_job_async(job_id)
            if job.status in {
                JobStatus.RUNNING,
                JobStatus.PAUSED,
                JobStatus.FAILED,
            }:
                return False
            if job.status not in {JobStatus.CANCELLED, JobStatus.COMPLETED}:
                return False
        if self.jobs.get(job_id) is not job:
            return False
        del self.jobs[job_id]
        return True

    def start_job(self, job_id: str) -> bool:
        """Start executing a job."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.mission_id = None
        job.progress = JobProgress()
        job.result_message = None
        job.error_message = None

        task = loop.create_task(self._execute_job(job), name=f"job-execute:{job.id}")
        self._running_tasks.add(task)
        self._job_tasks[job.id] = task
        task.add_done_callback(self._running_tasks.discard)
        task.add_done_callback(lambda done, job_id=job.id: self._on_job_task_done(job_id, done))
        return True

    def _on_job_task_done(self, job_id: str, task: asyncio.Task) -> None:
        """Log any unhandled exception from a job task."""
        if self._job_tasks.get(job_id) is task:
            self._job_tasks.pop(job_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Unhandled exception in job task: %s", exc, exc_info=exc)

    def _schedule_control_task(
        self,
        job_id: str,
        operation: str,
        coroutine_factory: Callable[[], Coroutine[Any, Any, bool]],
    ) -> bool:
        """Schedule one compatibility operation without returning a truthy no-op."""
        if job_id in self._job_control_tasks:
            return False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False

        coroutine = coroutine_factory()
        try:
            task = loop.create_task(coroutine, name=f"job-{operation}:{job_id}")
        except Exception:
            coroutine.close()
            logger.exception("Could not schedule %s for job %s", operation, job_id)
            return False

        self._job_control_tasks[job_id] = task
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        task.add_done_callback(
            lambda done, target=job_id, action=operation: self._on_control_task_done(
                target,
                action,
                done,
            )
        )
        return True

    def _on_control_task_done(
        self,
        job_id: str,
        operation: str,
        task: asyncio.Task[bool],
    ) -> None:
        if self._job_control_tasks.get(job_id) is task:
            self._job_control_tasks.pop(job_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Unhandled exception in job %s operation: %s",
                operation,
                exc,
                exc_info=exc,
            )

    def pause_job(self, job_id: str) -> bool:
        """Schedule a linked mission pause for legacy synchronous callers."""
        job = self.jobs.get(job_id)
        if (
            job is None
            or job.status != JobStatus.RUNNING
            or not job.mission_id
            or self._mission_service is None
        ):
            return False
        return self._schedule_control_task(
            job_id,
            "pause",
            lambda: self.pause_job_async(job_id),
        )

    async def pause_job_async(self, job_id: str) -> bool:
        """Pause a running job through its linked MissionService mission."""
        job = self.jobs.get(job_id)
        if (
            not job
            or job.status != JobStatus.RUNNING
            or not job.mission_id
            or self._mission_service is None
        ):
            return False

        try:
            await self._mission_service.pause_mission(job.mission_id)
            mission_status = await self._mission_service.get_mission_status(job.mission_id)
        except Exception as exc:
            job.error_message = f"Pause failed: {exc}"
            logger.error("Job %s pause failed: %s", job.id, exc, exc_info=True)
            return False

        status = self._mission_status_value(mission_status)
        if status == MissionLifecycleStatus.PAUSED:
            job.status = JobStatus.PAUSED
            job.error_message = None
            return True
        if status in {MissionLifecycleStatus.FAILED, MissionLifecycleStatus.ABORTED}:
            self._project_terminal_status(job, mission_status)
        return False

    def resume_job(self, job_id: str) -> bool:
        """Schedule a linked mission resume for legacy synchronous callers."""
        job = self.jobs.get(job_id)
        if (
            job is None
            or job.status != JobStatus.PAUSED
            or not job.mission_id
            or self._mission_service is None
        ):
            return False
        return self._schedule_control_task(
            job_id,
            "resume",
            lambda: self.resume_job_async(job_id),
        )

    async def resume_job_async(self, job_id: str) -> bool:
        """Resume a paused job through its linked MissionService mission."""
        job = self.jobs.get(job_id)
        if (
            not job
            or job.status != JobStatus.PAUSED
            or not job.mission_id
            or self._mission_service is None
        ):
            return False

        try:
            await self._mission_service.resume_mission(job.mission_id)
            mission_status = await self._mission_service.get_mission_status(job.mission_id)
        except Exception as exc:
            job.error_message = f"Resume failed: {exc}"
            logger.error("Job %s resume failed: %s", job.id, exc, exc_info=True)
            return False

        if self._mission_status_value(mission_status) == MissionLifecycleStatus.RUNNING:
            job.status = JobStatus.RUNNING
            job.error_message = None
            return True
        return False

    def cancel_job(self, job_id: str) -> bool:
        """Schedule cancellation for legacy synchronous callers."""
        job = self.jobs.get(job_id)
        if job is None or job.status in {
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
            JobStatus.FAILED,
        }:
            return False
        if job.status == JobStatus.PENDING:
            self._finalize_cancelled(job, "Job cancelled before mission start")
            return True
        if job.status in {JobStatus.RUNNING, JobStatus.PAUSED}:
            if job.mission_id and self._mission_service is None:
                return False
            if not job.mission_id and job_id not in self._job_tasks:
                return False
        return self._schedule_control_task(
            job_id,
            "cancel",
            lambda: self.cancel_job_async(job_id),
        )

    async def cancel_job_async(self, job_id: str) -> bool:
        """Cancel a job and confirm its linked mission reaches a terminal state."""
        job = self.jobs.get(job_id)
        if not job or job.status in {
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
            JobStatus.FAILED,
        }:
            return False

        if job.status == JobStatus.PENDING:
            self._finalize_cancelled(job, "Job cancelled before mission start")
            return True

        task = self._job_tasks.get(job_id)
        if task is None:
            if job.mission_id and self._mission_service is not None:
                try:
                    mission_status = await self._abort_linked_mission(job)
                except Exception as exc:
                    self._finalize_failed(job, f"Mission cancellation failed: {exc}")
                    return False
                if mission_status is not None:
                    self._project_terminal_status(job, mission_status)
                    return job.status == JobStatus.CANCELLED
            self._finalize_failed(job, "Cancellation could not confirm mission state")
            return False

        if job.mission_id is None:
            # A task cancelled before its coroutine first runs cannot execute a
            # cancellation handler, so record the truthful no-mission outcome now.
            self._finalize_cancelled(job, "Job cancelled before mission start")
        else:
            job.result_message = "Cancellation requested; awaiting confirmed mission stop"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        if job.status in {JobStatus.RUNNING, JobStatus.PAUSED}:
            try:
                mission_status = await self._abort_linked_mission(job)
            except Exception as exc:
                self._finalize_failed(job, f"Mission cancellation failed: {exc}")
                return False
            if mission_status is not None:
                self._project_terminal_status(job, mission_status)
            else:
                self._finalize_failed(job, "Cancellation could not confirm mission state")
        return job.status == JobStatus.CANCELLED

    def get_next_scheduled_jobs(self, limit: int = 10) -> list[Job]:
        """Get next jobs scheduled to run."""
        now = datetime.now(UTC)
        scheduled_jobs = [
            job
            for job in self.jobs.values()
            if job.status == JobStatus.PENDING
            and job.enabled
            and job.scheduled_for
            and job.scheduled_for <= now
        ]

        # Sort by priority then scheduled time
        scheduled_jobs.sort(key=lambda j: (-j.priority.value, j.scheduled_for))
        return scheduled_jobs[:limit]

    async def start_scheduler(self):
        """Start the job scheduler."""
        if self.scheduler_running:
            return

        await self._recover_planning_occurrences()
        self.scheduler_running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop_scheduler(self):
        """Stop the job scheduler."""
        self.scheduler_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None

    async def shutdown(self) -> None:
        """Stop scheduling and safely cancel all active in-memory jobs."""
        await self.stop_scheduler()
        if self._job_control_tasks:
            await asyncio.gather(*list(self._job_control_tasks.values()), return_exceptions=True)
        active_job_ids = [
            job.id
            for job in self.jobs.values()
            if job.status in {JobStatus.RUNNING, JobStatus.PAUSED}
        ]
        if active_job_ids:
            await asyncio.gather(
                *(self.cancel_job_async(job_id) for job_id in active_job_ids),
                return_exceptions=True,
            )
        for task in list(self._planning_occurrence_tasks.values()):
            task.cancel()
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        self._running_tasks.clear()
        self._job_tasks.clear()
        self._job_control_tasks.clear()
        self._planning_occurrence_tasks.clear()

    async def _scheduler_loop(self):
        """Main scheduler loop."""
        while self.scheduler_running:
            try:
                # Check for jobs to start
                jobs_to_start = self.get_next_scheduled_jobs(5)
                for job in jobs_to_start:
                    self.start_job(job.id)

                # Update recurring job schedules
                self._update_recurring_schedules()

                # Clean up old completed jobs
                self._cleanup_old_jobs()

                # Dispatch planning jobs from persistence whose next_run has arrived.
                await self._check_and_dispatch_planning_jobs()

                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Scheduler loop error",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                observability.record_error(
                    origin="job_scheduler",
                    message="Scheduler loop error",
                    exception=e,
                    metadata={"context": "_scheduler_loop"},
                )
                await asyncio.sleep(60)

    async def _check_and_dispatch_planning_jobs(self) -> None:
        """Load planning jobs from persistence and fire any whose next_run has passed.

        ``next_run`` is computed dynamically from the stored ``schedule`` field
        rather than read from the DB (the DB has no ``next_run`` column).  This
        ensures jobs fire correctly after a server restart.

        Schedule field formats supported:
          - "HH:MM"  plain time string (legacy)
          - JSON SchedulePattern dict  (days_of_week, start_time, timezone, …)
        """
        if self._mission_service is None:
            # MissionService not wired yet; nothing to dispatch.
            return

        try:
            from ..core.persistence import persistence

            planning_jobs = persistence.load_planning_jobs()
        except Exception as exc:
            logger.warning("Could not load planning jobs for dispatch: %s", exc)
            return

        now = datetime.now(UTC)
        for job in planning_jobs:
            if not job.get("enabled", True):
                continue

            schedule_raw = job.get("schedule")
            if not schedule_raw:
                continue

            # --- Compute next_run dynamically from the schedule field ---
            try:
                import json as _json

                from ..models.job import Job as JobModel
                from ..models.job import SchedulePattern

                # The schedule column may hold a JSON SchedulePattern or a bare "HH:MM" string.
                if isinstance(schedule_raw, dict):
                    schedule_dict = schedule_raw
                else:
                    try:
                        schedule_dict = _json.loads(schedule_raw)
                    except (ValueError, TypeError):
                        # Treat as plain "HH:MM" string
                        schedule_dict = {"start_time": str(schedule_raw).strip()}

                schedule = SchedulePattern.model_validate(schedule_dict)
                # Build a minimal Job-like object for schedule calculations.
                job_obj = JobModel(
                    id=job.get("id", "tmp"), name=job.get("name", ""), schedule=schedule
                )
                due_occurrence = self._calculate_due_occurrence(job_obj, from_time=now)
            except Exception as exc:
                logger.warning(
                    "Planning job %r: failed to compute next_run from schedule %r — skipping. Error: %s",
                    job.get("id"),
                    schedule_raw,
                    exc,
                )
                continue

            if due_occurrence is None:
                continue

            # Don't re-fire if we already successfully started this occurrence.
            last_run_raw = job.get("last_run")
            if last_run_raw:
                try:
                    last_run = datetime.fromisoformat(last_run_raw)
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=UTC)
                    if last_run >= due_occurrence:
                        continue
                except (ValueError, TypeError):
                    pass  # Unparseable last_run — treat as never run

            try:
                await self._dispatch_scheduled_job(job, due_occurrence=due_occurrence)
            except RuntimeError:
                # MissionService guard — should not happen since we check above
                raise
            except Exception as exc:
                logger.error(
                    "Unhandled error dispatching planning job %r: %s",
                    job.get("id"),
                    exc,
                    exc_info=True,
                )

    def _update_recurring_schedules(self):
        """Update next_run times for recurring jobs."""
        now = datetime.now(UTC)

        for job in self.jobs.values():
            if (
                job.schedule
                and job.schedule.enabled
                and job.status == JobStatus.COMPLETED
                and job.enabled
            ):
                # Calculate next run time based on schedule
                next_run = self._calculate_next_run(job, now)
                if next_run:
                    job.next_run = next_run
                    job.scheduled_for = next_run
                    job.status = JobStatus.PENDING

    @staticmethod
    def _resolve_dst_gap(candidate: datetime, tz: zoneinfo.ZoneInfo) -> datetime:
        """Resolve a candidate datetime that may fall inside a DST gap.

        ``datetime.combine(..., tzinfo=ZoneInfo(...))`` with fold=0 can produce
        a wall-clock time that does not actually exist during spring-forward
        transitions.  We detect this by round-tripping through UTC: if the
        UTC→local conversion yields a different wall-clock time, the original
        was in the gap and we use the normalised (post-gap) result instead.
        """
        utc_equiv = candidate.astimezone(UTC)
        normalised = utc_equiv.astimezone(tz)
        # If wall-clock time changed, the original was in a DST gap.
        if normalised.hour != candidate.hour or normalised.minute != candidate.minute:
            return normalised
        return candidate

    def _calculate_next_run(self, job: Job, from_time: datetime) -> datetime | None:
        """Calculate next run time for a job in the operator's local timezone.

        Uses ``job.schedule.timezone`` (an IANA timezone string, e.g.
        ``"America/New_York"``) so that DST transitions and day-of-week checks
        are evaluated in wall-clock time rather than UTC.

        DST gap handling: if ``start_time`` falls in a skipped hour (spring-
        forward), the returned datetime is advanced to the first valid instant
        after the gap.  Fold (fall-back) ambiguity is resolved by ``fold=0``
        (the first occurrence, i.e. still in DST).

        Backward-compatible: existing records that were serialised without a
        ``timezone`` field get the default ``"UTC"``, so behaviour is unchanged
        for UTC-only deployments.
        """
        if not job.schedule or not job.schedule.start_time:
            return None

        tz = zoneinfo.ZoneInfo(job.schedule.timezone)

        # Normalise from_time into the operator's local timezone so that
        # day-of-week comparisons are done in wall-clock terms.
        now_local = from_time.astimezone(tz)
        today = now_local.date()

        def _make_candidate(date) -> datetime:
            """Build a DST-safe local datetime for *date* at start_time."""
            raw = datetime.combine(date, job.schedule.start_time, tzinfo=tz)
            return self._resolve_dst_gap(raw, tz)

        candidate = _make_candidate(today)

        # If today's candidate is already in the past (or right now), start
        # searching from tomorrow.
        if candidate <= now_local:
            candidate = _make_candidate(today + timedelta(days=1))

        # Advance day-by-day until we land on an allowed day-of-week.
        if job.schedule.days_of_week:
            # Safety cap: at most 7 iterations to find the next allowed day.
            for _ in range(7):
                if candidate.weekday() in job.schedule.days_of_week:
                    break
                candidate = _make_candidate(candidate.date() + timedelta(days=1))

        return candidate

    def _calculate_due_occurrence(self, job: Job, from_time: datetime) -> datetime | None:
        """Return the most recent scheduled occurrence that is due at ``from_time``."""
        if not job.schedule or not job.schedule.start_time:
            return None

        tz = zoneinfo.ZoneInfo(job.schedule.timezone)
        now_local = from_time.astimezone(tz)
        allowed_days = set(job.schedule.days_of_week or range(7))

        for offset in range(0, 8):
            candidate_date = now_local.date() - timedelta(days=offset)
            raw = datetime.combine(candidate_date, job.schedule.start_time, tzinfo=tz)
            candidate = self._resolve_dst_gap(raw, tz)
            if candidate.weekday() not in allowed_days:
                continue
            if candidate <= now_local:
                return candidate.astimezone(UTC)
        return None

    def _cleanup_old_jobs(self):
        """Remove old completed jobs."""
        cutoff_date = datetime.now(UTC) - timedelta(days=30)

        jobs_to_remove = [
            job_id
            for job_id, job in self.jobs.items()
            if job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED]
            and job.completed_at
            and job.completed_at < cutoff_date
        ]

        for job_id in jobs_to_remove:
            del self.jobs[job_id]

    async def _admit_job_mission(
        self,
        *,
        job_id: str,
        job_name: str,
        zones: list[str],
        pattern: str,
        pattern_params: dict[str, Any],
        mission_name: str,
        on_mission_allocated: Callable[[str], None] | None = None,
        on_mission_created: Callable[[str], None] | None = None,
    ) -> Mission:
        """Apply the canonical job gates, then create and start one mission."""
        if self._mission_service is None:
            raise _JobAdmissionBlocked(
                "JobsService: MissionService is not wired. "
                "Call set_mission_service() before dispatching scheduled jobs."
            )

        async with self._mission_admission_lock:
            if get_safety_state().get("emergency_stop_active", False):
                raise _JobAdmissionBlocked("emergency stop is active")

            if self._qualification_service is None:
                raise _JobAdmissionBlocked("qualification service is unavailable")
            try:
                self._qualification_service.assert_current()
            except Exception as exc:
                evaluation = getattr(exc, "evaluation", None)
                reason_codes = getattr(evaluation, "reason_codes", None) or [
                    "QUALIFICATION_EVIDENCE_MISSING"
                ]
                reason = ", ".join(str(code) for code in reason_codes)
                raise _JobAdmissionBlocked(
                    f"qualification evidence blocked start ({reason})"
                ) from exc

            try:
                missions = await self._mission_service.list_missions()
            except Exception as exc:
                raise _JobAdmissionBlocked(f"could not list missions: {exc}") from exc

            mission_statuses = getattr(self._mission_service, "mission_statuses", {})
            for existing_mission in missions:
                status = mission_statuses.get(existing_mission.id)
                if status is None:
                    continue
                status_value = self._mission_status_value(status)
                if status_value in {
                    MissionLifecycleStatus.RUNNING,
                    MissionLifecycleStatus.PAUSED,
                }:
                    raise _JobAdmissionBlocked(
                        f"mission {existing_mission.id} is already {status_value.value}"
                    )

            if not zones:
                raise _JobAdmissionBlocked("no zones configured")
            try:
                mission = await self._mission_service.create_mission(
                    name=mission_name,
                    zone_id=zones[0],
                    pattern=pattern,
                    pattern_params=pattern_params,
                )
            except Exception as exc:
                raise _JobAdmissionBlocked(f"create_mission failed: {exc}") from exc

            if on_mission_allocated is not None:
                on_mission_allocated(mission.id)

            try:
                await self._mission_service.start_mission(mission.id)
            except Exception as exc:
                cleanup_detail = ""
                try:
                    await self._mission_service.delete_mission(mission.id)
                except Exception as cleanup_exc:
                    cleanup_detail = f"; idle mission cleanup failed: {cleanup_exc}"
                raise _JobAdmissionBlocked(
                    f"start_mission({mission.id}) failed: {exc}{cleanup_detail}"
                ) from exc

            if on_mission_created is not None:
                on_mission_created(mission.id)

        return mission

    async def _broadcast_job_started(
        self,
        *,
        job_id: str,
        job_name: str,
        mission_id: str,
        zone_id: str,
    ) -> None:
        """Broadcast an accepted start without owning any authoritative state."""
        if self._websocket_hub is not None:
            try:
                await self._websocket_hub.broadcast_to_topic(
                    "planning.schedule.fired",
                    {
                        "job_id": job_id,
                        "job_name": job_name,
                        "mission_id": mission_id,
                        "zone_id": zone_id,
                        "fired_at": datetime.now(UTC).isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "Scheduled job %r (%s): WS broadcast failed (non-fatal): %s",
                    job_name,
                    job_id,
                    exc,
                )

    @staticmethod
    def _planning_occurrence_id(job_id: str, scheduled_for: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"lawnberry:{job_id}:{scheduled_for}"))

    @staticmethod
    def _find_persisted_planning_job(job_id: str) -> dict[str, Any] | None:
        from ..core.persistence import persistence

        return next(
            (job for job in persistence.load_planning_jobs() if job.get("id") == job_id),
            None,
        )

    @staticmethod
    def _planning_job_with_occurrence(job: dict[str, Any]) -> dict[str, Any]:
        """Project the latest durable occurrence onto the planning API record."""
        from ..core.persistence import persistence

        result = dict(job)
        occurrence = persistence.load_latest_planning_job_occurrence(str(job["id"]))
        result["occurrence"] = occurrence
        if occurrence is None:
            result.update(
                {
                    "mission_id": None,
                    "mission_ids": [],
                    "zones_completed": [],
                    "progress_percentage": 0.0,
                    "error_message": None,
                }
            )
            return result

        zones = list(job.get("zones") or [])
        zones_completed = list(occurrence.get("zones_completed") or [])
        result.update(
            {
                "status": occurrence["status"],
                "mission_id": occurrence.get("active_mission_id"),
                "mission_ids": list(occurrence.get("mission_ids") or []),
                "zones_completed": zones_completed,
                "progress_percentage": (
                    round(100.0 * len(zones_completed) / len(zones), 1) if zones else 0.0
                ),
                "error_message": occurrence.get("error_message"),
                "started_at": occurrence.get("started_at"),
                "completed_at": occurrence.get("completed_at"),
            }
        )
        return result

    def list_persisted_planning_jobs(self) -> list[dict[str, Any]]:
        from ..core.persistence import persistence

        return [self._planning_job_with_occurrence(job) for job in persistence.load_planning_jobs()]

    def get_persisted_planning_job(self, job_id: str) -> dict[str, Any] | None:
        job = self._find_persisted_planning_job(job_id)
        return self._planning_job_with_occurrence(job) if job is not None else None

    def _launch_planning_occurrence(
        self,
        job: dict[str, Any],
        occurrence: dict[str, Any],
        mission: Mission | None,
    ) -> None:
        occurrence_id = str(occurrence["occurrence_id"])
        existing = self._planning_occurrence_tasks.get(occurrence_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(
            self._execute_planning_occurrence(dict(job), occurrence, mission),
            name=f"planning-occurrence:{occurrence_id}",
        )
        self._planning_occurrence_tasks[occurrence_id] = task
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        task.add_done_callback(
            lambda _done, target=occurrence_id: self._planning_occurrence_tasks.pop(target, None)
        )

    async def _recover_planning_occurrences(self) -> None:
        """Reconcile interrupted occurrences with MissionService restart truth."""
        from ..core.persistence import persistence

        if self._mission_service is None:
            return
        for occurrence in persistence.load_active_planning_job_occurrences():
            job = self._find_persisted_planning_job(str(occurrence["job_id"]))
            if job is None:
                persistence.update_planning_job_occurrence(
                    occurrence["occurrence_id"],
                    status="failed",
                    completed_at=datetime.now(UTC).isoformat(),
                    error_message="Planning job was deleted during an active occurrence",
                )
                continue

            mission: Mission | None = None
            mission_id = occurrence.get("active_mission_id")
            if mission_id:
                mission = getattr(self._mission_service, "missions", {}).get(mission_id)
                if mission is None:
                    persistence.update_planning_job_occurrence(
                        occurrence["occurrence_id"],
                        status="failed",
                        active_mission_id=None,
                        completed_at=datetime.now(UTC).isoformat(),
                        error_message=f"Linked mission {mission_id} is unavailable after restart",
                    )
                    job["status"] = "failed"
                    persistence.save_planning_job(job)
                    continue
                mission_status = await self._mission_service.get_mission_status(mission_id)
                lifecycle = self._mission_status_value(mission_status)
                if lifecycle == MissionLifecycleStatus.IDLE:
                    await self._mission_service.delete_mission(mission_id)
                    persistence.update_planning_job_occurrence(
                        occurrence["occurrence_id"],
                        status="blocked",
                        active_mission_id=None,
                        completed_at=datetime.now(UTC).isoformat(),
                        error_message="Restart interrupted mission admission before start acceptance",
                    )
                    job["status"] = "failed"
                    persistence.save_planning_job(job)
                    continue
                if lifecycle == MissionLifecycleStatus.PAUSED:
                    occurrence = persistence.update_planning_job_occurrence(
                        occurrence["occurrence_id"], status="paused"
                    )
                    job["status"] = "paused"
                    persistence.save_planning_job(job)
            elif occurrence["status"] == "pending":
                persistence.update_planning_job_occurrence(
                    occurrence["occurrence_id"],
                    status="blocked",
                    completed_at=datetime.now(UTC).isoformat(),
                    error_message="Restart interrupted occurrence before mission identity was persisted",
                )
                job["status"] = "failed"
                persistence.save_planning_job(job)
                continue

            self._launch_planning_occurrence(job, occurrence, mission)

    async def _start_planning_occurrence(
        self,
        job: dict[str, Any],
        *,
        scheduled_for: datetime,
        mission_name_prefix: str | None = None,
    ) -> tuple[dict[str, Any], Mission | None]:
        """Claim and admit the first mission for one durable occurrence."""
        from ..core.persistence import persistence

        if not job.get("enabled", True):
            raise _JobAdmissionBlocked("planning job is disabled")
        zones = list(job.get("zones") or [])
        if not zones:
            raise _JobAdmissionBlocked("no zones configured")

        scheduled_key = scheduled_for.astimezone(UTC).isoformat()
        occurrence, created = persistence.claim_planning_job_occurrence(
            occurrence_id=self._planning_occurrence_id(str(job["id"]), scheduled_key),
            job_id=str(job["id"]),
            scheduled_for=scheduled_key,
        )
        if not created:
            return occurrence, None

        def record_allocated_mission(mission_id: str) -> None:
            persistence.update_planning_job_occurrence(
                occurrence["occurrence_id"],
                mission_ids=[mission_id],
                active_mission_id=mission_id,
            )

        try:
            mission = await self._admit_job_mission(
                job_id=str(job["id"]),
                job_name=str(job.get("name") or "Planning job"),
                zones=[zones[0]],
                pattern=str(job.get("pattern") or "parallel"),
                pattern_params=dict(job.get("pattern_params") or {}),
                mission_name=(
                    f"{mission_name_prefix or job.get('name', 'Planning job')} — "
                    f"zone 1/{len(zones)}"
                    if len(zones) > 1
                    else str(mission_name_prefix or job.get("name") or "Planning job")
                ),
                on_mission_allocated=record_allocated_mission,
            )
        except Exception as exc:
            occurrence = persistence.update_planning_job_occurrence(
                occurrence["occurrence_id"],
                status="blocked",
                active_mission_id=None,
                completed_at=datetime.now(UTC).isoformat(),
                error_message=str(exc),
            )
            job["status"] = "failed"
            persistence.save_planning_job(job)
            if isinstance(exc, _JobAdmissionBlocked):
                return occurrence, None
            raise

        now = datetime.now(UTC).isoformat()
        occurrence = persistence.update_planning_job_occurrence(
            occurrence["occurrence_id"],
            status="running",
            zone_index=0,
            mission_ids=[mission.id],
            active_mission_id=mission.id,
            started_at=now,
            error_message=None,
        )
        job["status"] = "running"
        job["last_run"] = scheduled_key
        persistence.save_planning_job(job)

        self._launch_planning_occurrence(job, occurrence, mission)
        return occurrence, mission

    async def _execute_planning_occurrence(
        self,
        job: dict[str, Any],
        occurrence: dict[str, Any],
        first_mission: Mission | None,
    ) -> None:
        """Execute ordered zone missions and aggregate only confirmed terminal truth."""
        from ..core.persistence import persistence

        if self._mission_service is None:  # pragma: no cover - admission already enforces this
            return

        zones = list(job.get("zones") or [])
        mission = first_mission
        mission_ids = list(occurrence.get("mission_ids") or [])
        zones_completed = list(occurrence.get("zones_completed") or [])
        occurrence_id = str(occurrence["occurrence_id"])
        start_index = max(0, int(occurrence.get("zone_index") or 0))

        try:
            for zone_index in range(start_index, len(zones)):
                zone_id = zones[zone_index]
                if mission is None:

                    def record_allocated_mission(
                        mission_id: str,
                        current_zone_index: int = zone_index,
                    ) -> None:
                        allocated_ids = [*mission_ids, mission_id]
                        persistence.update_planning_job_occurrence(
                            occurrence_id,
                            zone_index=current_zone_index,
                            mission_ids=allocated_ids,
                            active_mission_id=mission_id,
                        )

                    mission = await self._admit_job_mission(
                        job_id=str(job["id"]),
                        job_name=str(job.get("name") or "Planning job"),
                        zones=[zone_id],
                        pattern=str(job.get("pattern") or "parallel"),
                        pattern_params=dict(job.get("pattern_params") or {}),
                        mission_name=(
                            f"{job.get('name', 'Planning job')} — "
                            f"zone {zone_index + 1}/{len(zones)}"
                        ),
                        on_mission_allocated=record_allocated_mission,
                    )
                    mission_ids.append(mission.id)
                    persistence.update_planning_job_occurrence(
                        occurrence_id,
                        status="running",
                        zone_index=zone_index,
                        mission_ids=mission_ids,
                        active_mission_id=mission.id,
                    )
                    await self._broadcast_job_started(
                        job_id=str(job["id"]),
                        job_name=str(job.get("name") or "Planning job"),
                        mission_id=mission.id,
                        zone_id=str(zone_id),
                    )

                terminal = await self._mission_service.wait_for_terminal_state(mission.id)
                terminal_status = self._mission_status_value(terminal)
                if terminal_status != MissionLifecycleStatus.COMPLETED:
                    state = (
                        "cancelled"
                        if terminal_status == MissionLifecycleStatus.ABORTED
                        else "failed"
                    )
                    detail = terminal.detail or (
                        f"Mission {mission.id} ended in {terminal_status.value}"
                    )
                    persistence.update_planning_job_occurrence(
                        occurrence_id,
                        status=state,
                        active_mission_id=None,
                        completed_at=datetime.now(UTC).isoformat(),
                        error_message=detail,
                    )
                    job["status"] = state
                    persistence.save_planning_job(job)
                    return

                zones_completed.append(str(zone_id))
                persistence.update_planning_job_occurrence(
                    occurrence_id,
                    zone_index=zone_index + 1,
                    zones_completed=zones_completed,
                    active_mission_id=None,
                )
                mission = None

            persistence.update_planning_job_occurrence(
                occurrence_id,
                status="completed",
                active_mission_id=None,
                completed_at=datetime.now(UTC).isoformat(),
                error_message=None,
            )
            job["status"] = "completed"
            persistence.save_planning_job(job)
        except asyncio.CancelledError:
            try:
                if mission is not None:
                    status = await self._mission_service.get_mission_status(mission.id)
                    if self._mission_status_value(status) in {
                        MissionLifecycleStatus.RUNNING,
                        MissionLifecycleStatus.PAUSED,
                    }:
                        await self._mission_service.abort_mission(mission.id)
                persistence.update_planning_job_occurrence(
                    occurrence_id,
                    status="cancelled",
                    active_mission_id=None,
                    completed_at=datetime.now(UTC).isoformat(),
                    error_message="Planning occurrence cancelled during shutdown",
                )
                job["status"] = "cancelled"
                persistence.save_planning_job(job)
            except Exception as exc:
                persistence.update_planning_job_occurrence(
                    occurrence_id,
                    status="failed",
                    completed_at=datetime.now(UTC).isoformat(),
                    error_message=f"Shutdown stop could not be confirmed: {exc}",
                )
            raise
        except Exception as exc:
            persistence.update_planning_job_occurrence(
                occurrence_id,
                status="failed",
                active_mission_id=None,
                completed_at=datetime.now(UTC).isoformat(),
                error_message=str(exc),
            )
            job["status"] = "failed"
            persistence.save_planning_job(job)
            logger.error(
                "Planning occurrence %s failed: %s",
                occurrence_id,
                exc,
                exc_info=True,
            )

    async def start_persisted_planning_job(self, job_id: str) -> dict[str, Any]:
        """Start a one-off planning job and return authoritative persisted state."""
        job = self._find_persisted_planning_job(job_id)
        if job is None:
            raise KeyError(job_id)
        created_at = datetime.fromisoformat(str(job.get("created_at")))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        occurrence, mission = await self._start_planning_occurrence(
            job,
            scheduled_for=created_at,
        )
        if mission is not None:
            asyncio.create_task(
                self._broadcast_job_started(
                    job_id=str(job["id"]),
                    job_name=str(job.get("name") or "Planning job"),
                    mission_id=mission.id,
                    zone_id=str(list(job.get("zones") or [""])[0]),
                )
            )
        state = self.get_persisted_planning_job(job_id)
        if state is None:  # pragma: no cover - job was loaded above
            raise KeyError(job_id)
        state["occurrence"] = occurrence
        return state

    async def control_persisted_planning_job(
        self,
        job_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Pause, resume, or cancel the active child mission with confirmation."""
        from ..core.persistence import persistence

        if self._mission_service is None:
            raise _JobAdmissionBlocked("mission service is unavailable")
        job = self._find_persisted_planning_job(job_id)
        if job is None:
            raise KeyError(job_id)
        occurrence = persistence.load_latest_planning_job_occurrence(job_id)
        if occurrence is None:
            raise _JobAdmissionBlocked("planning job has no occurrence")
        mission_id = occurrence.get("active_mission_id")

        if action == "pause":
            if occurrence["status"] != "running" or not mission_id:
                raise _JobAdmissionBlocked("planning job is not running")
            await self._mission_service.pause_mission(mission_id)
            confirmed = await self._mission_service.get_mission_status(mission_id)
            if self._mission_status_value(confirmed) != MissionLifecycleStatus.PAUSED:
                raise _JobAdmissionBlocked("mission pause was not confirmed")
            new_status = "paused"
        elif action == "resume":
            if occurrence["status"] != "paused" or not mission_id:
                raise _JobAdmissionBlocked("planning job is not paused")
            await self._mission_service.resume_mission(mission_id)
            confirmed = await self._mission_service.get_mission_status(mission_id)
            if self._mission_status_value(confirmed) != MissionLifecycleStatus.RUNNING:
                raise _JobAdmissionBlocked("mission resume was not confirmed")
            new_status = "running"
        elif action == "cancel":
            if occurrence["status"] not in {"pending", "running", "paused"}:
                raise _JobAdmissionBlocked("planning job is already terminal")
            if mission_id:
                await self._mission_service.abort_mission(mission_id)
                confirmed = await self._mission_service.get_mission_status(mission_id)
                if self._mission_status_value(confirmed) not in {
                    MissionLifecycleStatus.ABORTED,
                    MissionLifecycleStatus.FAILED,
                }:
                    raise _JobAdmissionBlocked("mission cancellation was not confirmed")
            new_status = "cancelled"
        else:
            raise ValueError(f"Unsupported planning action: {action}")

        terminal_updates: dict[str, Any] = {}
        if new_status == "cancelled":
            terminal_updates = {
                "active_mission_id": None,
                "completed_at": datetime.now(UTC).isoformat(),
                "error_message": "Cancelled by operator",
            }
        persistence.update_planning_job_occurrence(
            occurrence["occurrence_id"],
            status=new_status,
            **terminal_updates,
        )
        job["status"] = new_status
        persistence.save_planning_job(job)
        state = self.get_persisted_planning_job(job_id)
        if state is None:  # pragma: no cover - job was loaded above
            raise KeyError(job_id)
        return state

    async def _dispatch_scheduled_job(
        self,
        job: dict[str, Any],
        *,
        due_occurrence: datetime | None = None,
    ) -> Mission | None:
        """Create and start a mission when a persistence-backed job fires."""
        job_id = job.get("id", "<unknown>")
        job_name = job.get("name", "<unnamed>")
        try:
            _occurrence, mission = await self._start_planning_occurrence(
                job,
                scheduled_for=due_occurrence or datetime.now(UTC),
                mission_name_prefix=f"Scheduled: {job_name}",
            )
        except _JobAdmissionBlocked as exc:
            logger.warning("Scheduled job %r (%s) skipped: %s.", job_name, job_id, exc)
            return None
        if mission is None:
            return None

        logger.info(
            "Scheduled job %r (%s) dispatched → mission %s started.",
            job_name,
            job_id,
            mission.id,
        )
        await self._broadcast_job_started(
            job_id=job_id,
            job_name=job_name,
            mission_id=mission.id,
            zone_id=list(job.get("zones") or [""])[0],
        )
        return mission

    async def _execute_job(self, job: Job) -> None:
        """Execute an in-memory job through the canonical MissionService lifecycle."""
        try:
            job_type = job.job_type if isinstance(job.job_type, JobType) else JobType(job.job_type)
            if job_type not in _MISSION_JOB_TYPES:
                raise _JobAdmissionBlocked(
                    f"job type {job_type.value!r} has no MissionService executor"
                )
            if not job.zones:
                raise _JobAdmissionBlocked("no zones configured")

            deadline = (
                asyncio.get_running_loop().time() + job.timeout_minutes * 60
                if job.timeout_minutes and job.timeout_minutes > 0
                else None
            )
            for zone_index, zone_id in enumerate(job.zones):
                mission = await self._admit_job_mission(
                    job_id=job.id,
                    job_name=job.name,
                    zones=[zone_id],
                    pattern=job.cutting_pattern,
                    pattern_params=dict(job.parameters),
                    mission_name=(
                        f"Job: {job.name} — zone {zone_index + 1}/{len(job.zones)}"
                        if len(job.zones) > 1
                        else f"Job: {job.name}"
                    ),
                    on_mission_created=lambda mission_id: setattr(job, "mission_id", mission_id),
                )
                if job.last_run is None:
                    job.last_run = datetime.now(UTC)
                job.execution_logs.append(f"Mission {mission.id} accepted for zone {zone_id}")
                job.result_message = (
                    f"Mission {mission.id} running"
                    if len(job.zones) == 1
                    else f"Mission {mission.id} running for zone {zone_id}"
                )

                await self._broadcast_job_started(
                    job_id=job.id,
                    job_name=job.name,
                    mission_id=mission.id,
                    zone_id=zone_id,
                )

                wait_for_terminal = self._mission_service.wait_for_terminal_state(mission.id)
                if deadline is not None:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    async with asyncio.timeout(remaining):
                        mission_status = await wait_for_terminal
                else:
                    mission_status = await wait_for_terminal
                self._project_terminal_status(job, mission_status, zone_id=zone_id)
                if self._mission_status_value(mission_status) != MissionLifecycleStatus.COMPLETED:
                    return
        except TimeoutError:
            detail = f"Mission exceeded job timeout of {job.timeout_minutes} minutes"
            try:
                mission_status = await self._abort_linked_mission(job)
            except Exception as abort_exc:
                self._finalize_failed(
                    job,
                    f"{detail}; mission stop could not be confirmed: {abort_exc}",
                )
            else:
                if mission_status is not None and mission_status.detail:
                    detail = f"{detail}: {mission_status.detail}"
                self._finalize_failed(job, detail)
        except asyncio.CancelledError:
            try:
                mission_status = await asyncio.shield(self._abort_linked_mission(job))
                if (
                    mission_status is None
                    or self._mission_status_value(mission_status) == MissionLifecycleStatus.IDLE
                ):
                    self._finalize_cancelled(job, "Job cancelled before mission start")
                else:
                    self._project_terminal_status(job, mission_status)
            except Exception as exc:
                self._finalize_failed(job, f"Mission cancellation failed: {exc}")
        except Exception as exc:
            try:
                mission_status = await self._abort_linked_mission(job)
            except Exception as abort_exc:
                self._finalize_failed(job, f"{exc}; mission cleanup failed: {abort_exc}")
            else:
                detail = str(exc)
                if (
                    mission_status is not None
                    and self._mission_status_value(mission_status) == MissionLifecycleStatus.FAILED
                    and mission_status.detail
                ):
                    detail = f"{detail}; {mission_status.detail}"
                self._finalize_failed(job, detail)
        finally:
            self._update_job_runtime(job)

    async def _abort_linked_mission(self, job: Job) -> MissionStatus | None:
        if self._mission_service is None or not job.mission_id:
            return None
        mission_status = await self._mission_service.get_mission_status(job.mission_id)
        status = self._mission_status_value(mission_status)
        if status in {MissionLifecycleStatus.RUNNING, MissionLifecycleStatus.PAUSED}:
            await self._mission_service.abort_mission(job.mission_id)
            mission_status = await self._mission_service.get_mission_status(job.mission_id)
        return mission_status

    @staticmethod
    def _mission_status_value(status: MissionStatus) -> MissionLifecycleStatus:
        value = status.status
        return value if isinstance(value, MissionLifecycleStatus) else MissionLifecycleStatus(value)

    def _project_terminal_status(
        self,
        job: Job,
        mission_status: MissionStatus,
        *,
        zone_id: str | None = None,
    ) -> None:
        status = self._mission_status_value(mission_status)
        if job.progress is None:
            job.progress = JobProgress()
        job.progress.percentage_complete = mission_status.completion_percentage
        current_zone = zone_id or (job.zones[0] if job.zones else None)
        job.progress.current_zone = current_zone

        if status == MissionLifecycleStatus.COMPLETED:
            if current_zone and current_zone not in job.progress.zones_completed:
                job.progress.zones_completed.append(current_zone)
            completed_count = len(job.progress.zones_completed)
            total_count = max(1, len(job.zones))
            job.progress.percentage_complete = min(100.0, 100.0 * completed_count / total_count)
            if completed_count >= len(job.zones):
                job.status = JobStatus.COMPLETED
                job.result_message = (
                    f"Mission {mission_status.mission_id} completed successfully"
                    if len(job.zones) == 1
                    else f"All {completed_count} zone missions completed successfully"
                )
            else:
                job.status = JobStatus.RUNNING
                job.result_message = (
                    f"Mission {mission_status.mission_id} completed; "
                    f"{completed_count}/{len(job.zones)} zones done"
                )
            job.error_message = None
        elif status == MissionLifecycleStatus.ABORTED:
            self._finalize_cancelled(
                job,
                mission_status.detail or f"Mission {mission_status.mission_id} aborted",
            )
            return
        elif status == MissionLifecycleStatus.FAILED:
            self._finalize_failed(
                job,
                mission_status.detail or f"Mission {mission_status.mission_id} failed",
            )
            return
        else:
            self._finalize_failed(job, f"Mission ended in unexpected state {status.value}")
            return

        job.completed_at = datetime.now(UTC)
        job.execution_logs.append(job.result_message)
        self._update_job_runtime(job)

    def _finalize_cancelled(self, job: Job, detail: str) -> None:
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        job.result_message = detail
        job.error_message = None
        job.execution_logs.append(detail)
        self._update_job_runtime(job)

    def _finalize_failed(self, job: Job, detail: str) -> None:
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.result_message = None
        job.error_message = detail
        job.execution_logs.append(f"Job failed: {detail}")
        self._update_job_runtime(job)

    @staticmethod
    def _update_job_runtime(job: Job) -> None:
        if job.progress is None or job.started_at is None:
            return
        end = job.completed_at or datetime.now(UTC)
        job.progress.runtime_minutes = max(0.0, (end - job.started_at).total_seconds() / 60.0)


# Global instance
jobs_service = JobsService()
