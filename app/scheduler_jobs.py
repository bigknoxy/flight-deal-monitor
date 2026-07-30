"""Scheduler job implementations."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.alert import telegram_bot
from app.alert_dispatch import _send_deal_alert
from app.config import config
from app.database import AsyncSessionLocal
from app.job_lifecycle import (
    RECONCILE_MAX_AGE_SECONDS,
    _complete_job_run,
    _fail_job_run,
    _start_job_run,
    reconcile_stale_job_runs,
)
from app.scanner import _scan_route
from app.utils.deduplication import cleanup_expired_deals
from app.utils.long_weekend import get_long_weekend_date_pairs

logger = logging.getLogger(__name__)

# Re-export extracted symbols for backward-compat imports / patch targets.
# (e.g. `from app.scheduler_jobs import reconcile_stale_job_runs` in older code
# paths, or tests that haven't migrated patch targets yet.)
__all__ = [
    "RECONCILE_MAX_AGE_SECONDS",
    "reconcile_stale_job_runs",
    "run_cleanup",
    "run_long_weekend_sweep",
    "run_mistake_sweep",
    "run_regular_sweep",
]

# Overall sweep timeout: 30 minutes. If a sweep takes longer than this, it's
# considered hung and will be cancelled. Individual route scans have their own
# 30s timeout in scanner.py.
SWEEP_TIMEOUT_SECONDS = 1800


@asynccontextmanager
async def _sweep_context(job_name: str) -> AsyncIterator[AsyncSession]:
    """Start a job run, yield a session, and complete/fail on exit."""
    job_run = await _start_job_run(job_name)
    try:
        async with AsyncSessionLocal() as session:
            yield session, job_run
    except Exception as e:
        logger.error(f"{job_name} failed: {e}")
        await telegram_bot.send_error_alert(f"{job_name} failed: {e}")
        await _fail_job_run(job_run, str(e))
        return
    await _complete_job_run(job_run, 0, 0)


async def _scan_and_alert(
    session: AsyncSession,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    route_suffix: str = "",
    deal_type_filter: str | None = None,
) -> tuple[int, int]:
    """Scan a single route and send alerts. Returns (deals_detected, alerts_sent)."""
    deals = await _scan_route(
        session,
        origin,
        destination,
        departure_date,
        return_date=return_date,
        route_suffix=route_suffix,
    )
    deals_detected = 0
    alerts_sent = 0
    for deal in deals:
        if deal_type_filter and deal.deal_type != deal_type_filter:
            continue
        deals_detected += 1
        _, a = await _send_deal_alert(session, deal)
        alerts_sent += a
    return deals_detected, alerts_sent


async def _run_concurrent_sweep(
    job_name: str,
    tasks: list[asyncio.Task],
    job_run: object | None = None,
) -> None:
    """Run a set of concurrent scan tasks with a semaphore and overall timeout."""
    if job_run is None:
        job_run = await _start_job_run(job_name)
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=SWEEP_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        for t in tasks:
            t.cancel()
        logger.error(f"{job_name} timed out after {SWEEP_TIMEOUT_SECONDS}s")
        await telegram_bot.send_error_alert(f"{job_name} timed out")
        await _fail_job_run(job_run, f"timed out after {SWEEP_TIMEOUT_SECONDS}s")
        return

    total_deals = 0
    total_alerts = 0
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
            logger.warning(f"{job_name} route scan failed: {r}")
        elif isinstance(r, tuple):
            total_deals += r[0]
            total_alerts += r[1]

    await _complete_job_run(job_run, total_deals, total_alerts)
    logger.info(
        f"{job_name} complete: {total_deals} deals, {total_alerts} alerts, "
        f"{errors} errors"
    )


async def run_regular_sweep() -> None:
    """Run regular flight price sweep with concurrent route scans."""
    logger.info("Starting regular flight price sweep")
    job_run = await _start_job_run("regular_sweep")
    semaphore = asyncio.Semaphore(config.app.max_concurrent_scans)

    async def _scan_route_wrapper(
        session: AsyncSession,
        origin: str,
        destination: str,
        departure_date: str,
    ) -> tuple[int, int]:
        async with semaphore:
            return await _scan_and_alert(session, origin, destination, departure_date)

    try:
        async with AsyncSessionLocal() as session:
            tasks = []
            for origin in config.app.home_airports:
                for destination in config.app.destinations:
                    for day_offset in range(0, config.app.look_ahead_days, 7):
                        departure_date = (
                            datetime.utcnow() + timedelta(days=day_offset)
                        ).strftime("%Y-%m-%d")
                        tasks.append(
                            asyncio.create_task(
                                _scan_route_wrapper(session, origin, destination, departure_date)
                            )
                        )
            await _run_concurrent_sweep("regular_sweep", tasks, job_run)
    except Exception as e:
        logger.error(f"Regular sweep failed: {e}")
        await telegram_bot.send_error_alert(f"Regular sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def run_mistake_sweep() -> None:
    """Run mistake fare sweep (higher priority, more frequent) with concurrent scans."""
    logger.info("Starting mistake fare sweep")
    job_run = await _start_job_run("mistake_sweep")
    semaphore = asyncio.Semaphore(config.app.max_concurrent_scans)

    async def _scan_route_wrapper(
        session: AsyncSession,
        origin: str,
        destination: str,
        departure_date: str,
    ) -> tuple[int, int]:
        async with semaphore:
            return await _scan_and_alert(
                session, origin, destination, departure_date,
                deal_type_filter="mistake_fare",
            )

    try:
        async with AsyncSessionLocal() as session:
            tasks = []
            for origin in config.app.home_airports:
                for destination in config.app.destinations:
                    for day_offset in range(0, 30):
                        departure_date = (
                            datetime.utcnow() + timedelta(days=day_offset)
                        ).strftime("%Y-%m-%d")
                        tasks.append(
                            asyncio.create_task(
                                _scan_route_wrapper(session, origin, destination, departure_date)
                            )
                        )
            await _run_concurrent_sweep("mistake_sweep", tasks, job_run)
    except Exception as e:
        logger.error(f"Mistake fare sweep failed: {e}")
        await telegram_bot.send_error_alert(f"Mistake fare sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def run_long_weekend_sweep() -> None:
    """Scan for long weekend deals (Thu→Sun, Fri→Mon) with concurrent scans."""
    logger.info("Starting long weekend sweep")
    job_run = await _start_job_run("long_weekend_sweep")
    semaphore = asyncio.Semaphore(config.app.max_concurrent_scans)

    date_pairs = get_long_weekend_date_pairs(
        config.app.long_weekend.look_ahead_months
    )

    async def _scan_route_wrapper(
        session: AsyncSession,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str,
    ) -> tuple[int, int]:
        async with semaphore:
            return await _scan_and_alert(
                session, origin, destination, departure_date,
                return_date=return_date, route_suffix="-long-weekend",
            )

    try:
        async with AsyncSessionLocal() as session:
            tasks = []
            for origin in config.app.home_airports:
                for destination in config.app.destinations:
                    for departure_date, return_date in date_pairs:
                        tasks.append(
                            asyncio.create_task(
                                _scan_route_wrapper(
                                    session, origin, destination, departure_date, return_date
                                )
                            )
                        )
            await _run_concurrent_sweep("long_weekend_sweep", tasks, job_run)
    except Exception as e:
        logger.error(f"Long weekend sweep failed: {e}")
        await telegram_bot.send_error_alert(f"Long weekend sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def run_cleanup() -> None:
    """Run cleanup of expired flight deals."""
    logger.info("Starting cleanup of expired deals")
    try:
        async with AsyncSessionLocal() as session:
            count = await cleanup_expired_deals(session)
            logger.info(f"Cleanup complete: removed {count} expired deals")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
