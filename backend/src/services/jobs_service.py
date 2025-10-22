import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from ..core.observability import observability
from ..models.job import Job, JobStatus, JobType, JobPriority
from ..models.zone import Zone


logger = observability.get_logger(__name__)


class JobsService:
    """Job scheduling and execution service."""
    
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.job_counter = 0
        self.scheduler_running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
    def create_job(self, name: str, job_type: JobType = JobType.SCHEDULED_MOW, 
                   zones: List[str] = None, priority: JobPriority = JobPriority.NORMAL,
                   **kwargs) -> Job:
        """Create a new job."""
        self.job_counter += 1
        job_id = f"job-{self.job_counter:04d}"
        
        job = Job(
            id=job_id,
            name=name,
            job_type=job_type,
            zones=zones or [],
            priority=priority,
            **kwargs
        )
        
        self.jobs[job_id] = job
        return job
        
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return self.jobs.get(job_id)
        
    def list_jobs(self, status: Optional[JobStatus] = None, 
                  job_type: Optional[JobType] = None) -> List[Job]:
        """List jobs with optional filtering."""
        jobs = list(self.jobs.values())
        
        if status:
            jobs = [job for job in jobs if job.status == status]
            
        if job_type:
            jobs = [job for job in jobs if job.job_type == job_type]
            
        # Sort by priority (high to low) then by created_at
        jobs.sort(key=lambda j: (-j.priority.value, j.created_at))
        return jobs
        
    def update_job(self, job_id: str, **updates) -> Optional[Job]:
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
        job.started_at = datetime.now(timezone.utc)
        
        # Start job execution (placeholder)
        asyncio.create_task(self._execute_job(job))
        return True
        
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
        job.completed_at = datetime.now(timezone.utc)
        return True
        
    def get_next_scheduled_jobs(self, limit: int = 10) -> List[Job]:
        """Get next jobs scheduled to run."""
        now = datetime.now(timezone.utc)
        scheduled_jobs = [
            job for job in self.jobs.values()
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
        now = datetime.now(timezone.utc)
        
        for job in self.jobs.values():
            if (job.schedule and job.schedule.enabled and 
                job.status == JobStatus.COMPLETED and 
                job.enabled):
                
                # Calculate next run time based on schedule
                next_run = self._calculate_next_run(job, now)
                if next_run:
                    job.next_run = next_run
                    job.scheduled_for = next_run
                    job.status = JobStatus.PENDING
                    
    def _calculate_next_run(self, job: Job, from_time: datetime) -> Optional[datetime]:
        """Calculate next run time for a job."""
        if not job.schedule or not job.schedule.start_time:
            return None
            
        # Simple daily scheduling (can be enhanced for more complex patterns)
        next_date = from_time.date() + timedelta(days=1)
        next_run = datetime.combine(next_date, job.schedule.start_time)
        next_run = next_run.replace(tzinfo=timezone.utc)
        
        # Check if this day is allowed
        if job.schedule.days_of_week:
            while next_run.weekday() not in job.schedule.days_of_week:
                next_run += timedelta(days=1)
                
        return next_run
        
    def _cleanup_old_jobs(self):
        """Remove old completed jobs."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=30)
        
        jobs_to_remove = [
            job_id for job_id, job in self.jobs.items()
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
                job.execution_logs.append(f"Step {i+1}/10 completed")
                
                await asyncio.sleep(1)  # Simulate work
                
            # Complete the job
            if job.status == JobStatus.RUNNING:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                job.last_run = job.completed_at
                job.result_message = "Job completed successfully"
                
        except Exception as e:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = str(e)
            job.execution_logs.append(f"Job failed: {e}")


# Global instance
jobs_service = JobsService()