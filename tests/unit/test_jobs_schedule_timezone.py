"""Tests for SchedulePattern.timezone field and _calculate_next_run DST fix.

TDD: these tests are written first, before the implementation.
"""
import zoneinfo
from datetime import datetime, time, timedelta

import pytest

from backend.src.models.job import Job, JobPriority, JobStatus, JobType, SchedulePattern
from backend.src.services.jobs_service import JobsService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(days_of_week: list[int], start_time: time, timezone: str = "UTC") -> Job:
    return Job(
        id="test-job-001",
        name="Test Job",
        job_type=JobType.SCHEDULED_MOW,
        schedule=SchedulePattern(
            days_of_week=days_of_week,
            start_time=start_time,
            timezone=timezone,
            enabled=True,
        ),
        status=JobStatus.PENDING,
        priority=JobPriority.NORMAL,
    )


# ---------------------------------------------------------------------------
# T1 — timezone field defaults to "UTC"
# ---------------------------------------------------------------------------

def test_schedule_pattern_timezone_default():
    sp = SchedulePattern(days_of_week=[0], start_time=time(8, 0))
    assert sp.timezone == "UTC"


def test_schedule_pattern_timezone_custom():
    sp = SchedulePattern(
        days_of_week=[0], start_time=time(8, 0), timezone="America/New_York"
    )
    assert sp.timezone == "America/New_York"


# ---------------------------------------------------------------------------
# T2 — next_run respects days_of_week in user TZ
#
# Scenario: it is Monday 07:50 AM New York time.
# The job is scheduled Monday at 08:00 AM America/New_York.
# Expected: next_run is within 10 minutes (not 24+ hours away).
# ---------------------------------------------------------------------------

def test_next_run_respects_days_of_week_in_user_tz():
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    service = JobsService()

    # A known Monday at 07:50 AM New York (non-DST: EST = UTC-5)
    # 2025-01-06 is a Monday
    from_time = datetime(2025, 1, 6, 7, 50, tzinfo=ny_tz)

    job = _make_job(
        days_of_week=[0],          # Monday (0 = Monday in Python's weekday())
        start_time=time(8, 0),
        timezone="America/New_York",
    )

    next_run = service._calculate_next_run(job, from_time)

    assert next_run is not None, "Expected a next_run datetime, got None"

    delta = next_run - from_time
    # Should fire in ~10 minutes, definitely NOT 24+ hours away
    assert delta >= timedelta(0), "next_run must be in the future"
    assert delta <= timedelta(minutes=15), (
        f"Expected next_run within 15 minutes of from_time, got delta={delta}"
    )

    # Result should be timezone-aware
    assert next_run.tzinfo is not None, "next_run must be timezone-aware"

    # The wall-clock hour/minute in New York should be 8:00
    next_run_local = next_run.astimezone(ny_tz)
    assert next_run_local.hour == 8
    assert next_run_local.minute == 0


# ---------------------------------------------------------------------------
# T3 — DST spring-forward: skipped hour is not returned
#
# 2025-03-09 in America/New_York: clocks jump from 2:00 AM to 3:00 AM.
# The hour 2:00–2:59 AM does not exist in New York that day.
#
# If a job is scheduled at 02:30 AM America/New_York on Sunday (weekday=6),
# the function must NOT return a datetime that lands in the skipped hour.
# Python's zoneinfo folds/gaps are handled automatically when you do
# datetime.combine(..., tzinfo=ZoneInfo(...)) — the non-existent 2:30 AM
# becomes 3:30 AM (fold=0 → resolved to post-gap).
# We just assert the returned time is >= 3:00 AM wall clock.
# ---------------------------------------------------------------------------

def test_next_run_in_local_tz_dst_spring_forward():
    """DST spring-forward: a start_time in the skipped hour is advanced past the gap.

    2025-03-09 (Sunday) in America/New_York: clocks jump from 2:00 AM to 3:00 AM.
    The hour 2:00–2:59 AM (wall clock) does not exist.

    A job scheduled at 02:30 AM that day must NOT produce a datetime whose UTC
    equivalent falls in the gap window (07:00–07:59 UTC on 2025-03-09).
    The implementation round-trips through UTC to detect the gap and returns the
    normalised post-gap time (3:30 AM EDT in this case).
    """
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    service = JobsService()

    # Spring-forward day is 2025-03-09 (Sunday).
    # We set from_time to 01:50 AM New York on that day (pre-spring-forward).
    from_time = datetime(2025, 3, 9, 1, 50, tzinfo=ny_tz)

    # Job: every Sunday (6) at 02:30 AM (skipped hour this day)
    job = _make_job(
        days_of_week=[6],          # Sunday
        start_time=time(2, 30),
        timezone="America/New_York",
    )

    next_run = service._calculate_next_run(job, from_time)

    assert next_run is not None, "Expected a next_run datetime, got None"
    assert next_run.tzinfo is not None, "next_run must be timezone-aware"

    # Must be on or after from_time
    assert next_run >= from_time, "next_run must be in the future"

    # The returned time must NOT show wall-clock hour 2 in New York on that day.
    # Hour 2 (2:00–2:59 AM) does not exist in New York on spring-forward day;
    # the implementation must advance past the gap.
    next_run_local = next_run.astimezone(ny_tz)
    assert next_run_local.date() == datetime(2025, 3, 9).date(), (
        f"Expected same Sunday 2025-03-09, got {next_run_local.date()}"
    )
    assert next_run_local.hour != 2, (
        f"next_run shows wall-clock hour 2 ({next_run_local}) in New York on "
        "spring-forward day — this time does not exist"
    )
    # Post-gap: 2:30 AM (gap) → 3:30 AM EDT (the first valid instant after the gap)
    assert next_run_local.hour == 3, (
        f"Expected post-gap hour 3 (3:30 AM EDT), got hour={next_run_local.hour}"
    )
    assert next_run_local.minute == 30


# ---------------------------------------------------------------------------
# T4 — Backward compat: existing jobs without timezone (defaults to UTC)
# ---------------------------------------------------------------------------

def test_next_run_backward_compat_utc_default():
    """Jobs without an explicit timezone default to UTC and still work."""
    from datetime import UTC

    service = JobsService()

    # A Monday in UTC
    from_time = datetime(2025, 1, 6, 7, 50, tzinfo=UTC)  # Monday 07:50 UTC

    # Build job using model fields directly (simulate old record with default tz)
    job = _make_job(
        days_of_week=[0],   # Monday
        start_time=time(8, 0),
        timezone="UTC",     # default
    )

    next_run = service._calculate_next_run(job, from_time)

    assert next_run is not None
    assert next_run.tzinfo is not None

    import zoneinfo as _zi
    utc_tz = _zi.ZoneInfo("UTC")
    next_run_utc = next_run.astimezone(utc_tz)
    assert next_run_utc.hour == 8
    assert next_run_utc.minute == 0

    delta = next_run - from_time
    assert timedelta(0) <= delta <= timedelta(minutes=15)


# ---------------------------------------------------------------------------
# T5 — When today's fire time is already past, schedule tomorrow (same TZ)
# ---------------------------------------------------------------------------

def test_next_run_already_past_today_schedules_next_week():
    """If today's fire time has passed, schedule the next occurrence."""
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    service = JobsService()

    # Monday 09:00 AM New York — the 08:00 slot has passed
    from_time = datetime(2025, 1, 6, 9, 0, tzinfo=ny_tz)

    job = _make_job(
        days_of_week=[0],   # Monday only
        start_time=time(8, 0),
        timezone="America/New_York",
    )

    next_run = service._calculate_next_run(job, from_time)

    assert next_run is not None
    next_run_local = next_run.astimezone(ny_tz)

    # Should fire next Monday (7 days later)
    expected_date = datetime(2025, 1, 13).date()
    assert next_run_local.date() == expected_date, (
        f"Expected next Monday 2025-01-13, got {next_run_local.date()}"
    )
    assert next_run_local.hour == 8
    assert next_run_local.minute == 0


# ---------------------------------------------------------------------------
# T6 — Invalid timezone string is rejected at model construction
# ---------------------------------------------------------------------------

def test_invalid_timezone_rejected():
    """SchedulePattern must raise ValueError for an unknown timezone string."""
    with pytest.raises(ValueError, match="Unknown timezone"):
        SchedulePattern(
            days_of_week=[0],
            start_time=time(8, 0),
            timezone="Not/ATimezone",
        )


# ---------------------------------------------------------------------------
# T7 — days_of_week out of range is rejected at model construction
# ---------------------------------------------------------------------------

def test_days_of_week_out_of_range_rejected():
    """SchedulePattern must reject days_of_week values outside 0–6."""
    with pytest.raises(ValueError, match="days_of_week"):
        SchedulePattern(
            days_of_week=[8],
            start_time=time(8, 0),
            timezone="UTC",
        )
