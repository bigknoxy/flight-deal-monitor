"""APScheduler setup for background jobs."""

import logging
import os
from urllib.parse import urlparse

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import config
from app.scheduler_jobs import (
    run_cleanup,
    run_long_weekend_sweep,
    run_mistake_sweep,
    run_regular_sweep,
)

logger = logging.getLogger(__name__)


def _ensure_jobstore_dir() -> None:
    """Ensure the SQLite job store directory exists."""
    jobstore_url = config.env.scheduler_jobstore_url
    if jobstore_url.startswith("sqlite"):
        parsed = urlparse(jobstore_url)
        db_path = parsed.path.lstrip("/")
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)


# Ensure job store directory exists before creating job store
_ensure_jobstore_dir()

# Job store for persistence
# Uses a separate SQLite file from app data to avoid lock contention.
# engine_options with connect_args sets busy_timeout for SQLite.
jobstores = {
    "default": SQLAlchemyJobStore(
        url=config.env.scheduler_jobstore_url,
        engine_options={"connect_args": {"timeout": 5}},
    )
}

# Executor
executors = {
    "default": AsyncIOExecutor(),
}

# Scheduler instance
scheduler = AsyncIOScheduler(
    jobstores=jobstores,
    executors=executors,
    job_defaults={
        "coalesce": config.app.job_coalesce,
        "max_instances": 1,
        "misfire_grace_time": 300,  # 5 minutes
    },
)


def start_scheduler() -> None:
    """Start the scheduler."""
    try:
        scheduler.start()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    try:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler shutdown gracefully")
    except Exception as e:
        logger.error(f"Error during scheduler shutdown: {e}")


def get_scheduler_status() -> dict:
    """Get scheduler status for health endpoint."""
    from datetime import datetime

    def _format(ts: datetime) -> str:
        # Stored as UTC by APScheduler; render in local time for human reading.
        try:
            from zoneinfo import ZoneInfo

            local = ts.astimezone(ZoneInfo("America/Chicago"))
        except Exception:
            local = ts
        return local.strftime("%Y-%m-%d %H:%M")

    jobs = []
    for job in scheduler.get_jobs():
        ts = job.next_run_time
        if ts is None:
            iso = None
            display = None
        else:
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    iso = None
                    display = None
                    jobs.append(
                        {
                            "id": job.id,
                            "name": job.name,
                            "next_run": None,
                            "next_run_display": None,
                        }
                    )
                    continue
            iso = ts.isoformat()
            display = _format(ts)
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run": iso,
                "next_run_display": display,
            }
        )
    return {
        "running": scheduler.running,
        "jobs": jobs,
        "job_count": len(jobs),
    }


def setup_jobs() -> None:
    """Set up scheduled jobs."""
    # Regular sweep every 30 minutes
    scheduler.add_job(
        run_regular_sweep,
        "interval",
        seconds=config.app.regular_sweep_interval,
        id="regular_sweep",
        name="Regular Flight Price Sweep",
        replace_existing=True,
    )

    # Mistake fare sweep every 15 minutes
    scheduler.add_job(
        run_mistake_sweep,
        "interval",
        seconds=config.app.mistake_sweep_interval,
        id="mistake_sweep",
        name="Mistake Fare Sweep",
        replace_existing=True,
    )

    # Daily cleanup of expired deals
    scheduler.add_job(
        run_cleanup,
        "interval",
        hours=24,
        id="cleanup",
        name="Expired Deal Cleanup",
        replace_existing=True,
    )

    # Long weekend sweep (opt-in)
    if config.app.long_weekend.enabled:
        scheduler.add_job(
            run_long_weekend_sweep,
            "interval",
            seconds=config.app.long_weekend.interval_minutes * 60,
            id="long_weekend_sweep",
            name="Long Weekend Deal Sweep",
            replace_existing=True,
        )
        logger.info("Long weekend sweep enabled")

    logger.info(f"Set up {len(scheduler.get_jobs())} scheduled jobs")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name} (ID: {job.id})")
