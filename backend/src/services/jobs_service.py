import asyncio
import zoneinfo
from datetime import UTC, datetime, timedelta

from ..core.observability import observability
from ..models.job import Job, JobPriority, JobStatus, JobType

logger = observability.get_logger(__name__)


class JobsService:
    """Job scheduling and execution service."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.job_counter = 0
        self.scheduler_running = False
        self._scheduler_task: asyncio.Task | None = None
        self._running_tasks: set[asyncio.Task] = set()

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
        """Delete a job."""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status == JobStatus.RUNNING:
                # Cancel running job first
                self.cancel_job(job_id)
            del self.jobs[job_id]
            return True
        return False

    def start_job(self, job_id: str) -> bool:
        """Start executing a job."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.PENDING:
            return False

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)

        task = asyncio.create_task(self._execute_job(job))
        self._running_tasks.add(task)
        task.add_done_callback(self._running_tasks.discard)
        task.add_done_callback(self._on_job_task_done)
        return True

    def _on_job_task_done(self, task: asyncio.Task) -> None:
        """Log any unhandled exception from a job task."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Unhandled exception in job task: %s", exc, exc_info=exc)

    def pause_job(self, job_id: str) -> bool:
        """Pause a running job."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.RUNNING:
            return False

        job.status = JobStatus.PAUSED
        return True

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.PAUSED:
            return False

        job.status = JobStatus.RUNNING
        return True

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        job = self.jobs.get(job_id)
        if not job or job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED]:
            return False

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        return True

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
        """Cancel all running job tasks and stop the scheduler."""
        await self.stop_scheduler()
        for task in list(self._running_tasks):
            task.cancel()
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks, return_exceptions=True)
        self._running_tasks.clear()

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
    def _resolve_dst_gap(candidate: datetime, tz: "zoneinfo.ZoneInfo") -> datetime:
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

    async def _execute_job(self, job: Job):
        """Execute a job (placeholder implementation)."""
        try:
            # Initialize progress
            if not job.progress:
                from ..models.job import JobProgress

                job.progress = JobProgress()

            # Simulate job execution
            for i in range(10):
                if job.status != JobStatus.RUNNING:
                    break

                # Update progress
                job.progress.percentage_complete = (i + 1) * 10
                job.progress.runtime_minutes = (i + 1) * 0.5

                # Add execution log
                job.execution_logs.append(f"Step {i + 1}/10 completed")

                await asyncio.sleep(1)  # Simulate work

            # Complete the job
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(UTC)
                job.last_run = job.completed_at
                job.result_message = "Job completed successfully"

        except Exception as e:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(UTC)
            job.error_message = str(e)
            job.execution_logs.append(f"Job failed: {e}")


# Global instance
jobs_service = JobsService()
