"""APScheduler setup for background jobs."""

import logging

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import config
from app.scheduler_jobs import run_mistake_sweep, run_regular_sweep

logger = logging.getLogger(__name__)


# Job store for persistence
jobstores = {
    "default": SQLAlchemyJobStore(url=config.env.database_url.replace("sqlite://", "sqlite:///"))
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
    return {
        "running": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            }
            for job in scheduler.get_jobs()
        ],
        "job_count": len(scheduler.get_jobs()),
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

    logger.info(f"Set up {len(scheduler.get_jobs())} scheduled jobs")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name} (ID: {job.id})")
