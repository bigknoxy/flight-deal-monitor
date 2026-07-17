"""Job run lifecycle helpers — start, complete, fail, and reconcile JobRun rows.

Extracted from scheduler_jobs.py as a pure mechanical refactor (no behavior
changes). These helpers each open their OWN AsyncSessionLocal session
(deliberately not the caller's) so a JobRun record survives even when the
sweep's own session is rolled back.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.job import JobRun

logger = logging.getLogger(__name__)

# A JobRun older than this (still "running") is treated as orphaned by a prior
# crash/SIGKILL and reconciled to "interrupted" on startup. 1h comfortably
# exceeds the longest sweep interval (regular=1800s) plus margin.
RECONCILE_MAX_AGE_SECONDS = 3600


async def reconcile_stale_job_runs() -> int:
    """Mark JobRun rows left ``running`` by a prior crash/KILL as ``interrupted``.

    APScheduler + the mistake/regular sweeps write a ``running`` row on start and
    flip it to a terminal state on completion. A ``SIGKILL``/OOM between those two
    leaves a row stuck ``running`` forever, which makes the dashboard's run
    history a lie. This runs once at startup and recovers those orphans.

    Returns the number of rows reconciled.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=RECONCILE_MAX_AGE_SECONDS)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(JobRun)
            .where(JobRun.completed_at.is_(None))
            .where(JobRun.started_at < cutoff)
        )
        stale = result.scalars().all()
        if not stale:
            return 0

        now = datetime.utcnow()
        for job in stale:
            job.status = "interrupted"
            job.completed_at = now
            job.error_message = "reconciled after restart (prior run did not complete)"
            session.add(job)
        await session.commit()

    logger.info(f"Reconciled {len(stale)} stale JobRun row(s) to 'interrupted'")
    return len(stale)


async def _start_job_run(job_id: str) -> JobRun:
    """Start a job run record."""
    async with AsyncSessionLocal() as session:
        job_run = JobRun(job_id=job_id)
        session.add(job_run)
        await session.commit()
        await session.refresh(job_run)
        return job_run


async def _complete_job_run(
    job_run: JobRun,
    deals_detected: int,
    alerts_sent: int,
) -> None:
    """Complete a job run record."""
    job_run.completed_at = datetime.utcnow()
    job_run.duration_seconds = (
        job_run.completed_at - job_run.started_at
    ).total_seconds()
    job_run.status = "success"
    job_run.deals_detected = deals_detected
    job_run.alerts_sent = alerts_sent

    async with AsyncSessionLocal() as session:
        # job_run was created in a different (now-closed) session. Re-adding a
        # detached instance that already has a primary key issues an UPDATE,
        # not a second INSERT, so no duplicate row is created.
        session.add(job_run)
        await session.commit()


async def _fail_job_run(job_run: JobRun, error_message: str) -> None:
    """Fail a job run record."""
    job_run.completed_at = datetime.utcnow()
    job_run.duration_seconds = (
        job_run.completed_at - job_run.started_at
    ).total_seconds()
    job_run.status = "failed"
    job_run.error_message = error_message

    async with AsyncSessionLocal() as session:
        session.add(job_run)
        await session.commit()
