"""Scheduler job implementations."""

import logging
from datetime import datetime, timedelta

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


async def run_regular_sweep() -> None:
    """Run regular flight price sweep."""
    logger.info("Starting regular flight price sweep")
    job_run = await _start_job_run("regular_sweep")

    try:
        deals_detected = 0
        alerts_sent = 0

        async with AsyncSessionLocal() as session:
            for origin in config.app.home_airports:
                for destination in config.app.destinations:
                    # Check dates for next 90 days
                    for day_offset in range(
                        0, config.app.look_ahead_days, 7
                    ):  # Weekly checks
                        departure_date = (
                            datetime.utcnow() + timedelta(days=day_offset)
                        ).strftime("%Y-%m-%d")

                        deals = await _scan_route(
                            session,
                            origin,
                            destination,
                            departure_date,
                        )

                        for deal in deals:
                            deals_detected += 1
                            d, a = await _send_deal_alert(session, deal)
                            alerts_sent += a

        await _complete_job_run(job_run, deals_detected, alerts_sent)
        logger.info(
            f"Regular sweep complete: {deals_detected} deals, {alerts_sent} alerts"
        )

    except Exception as e:
        logger.error(f"Regular sweep failed: {e}")
        await telegram_bot.send_error_alert(f"Regular sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def run_mistake_sweep() -> None:
    """Run mistake fare sweep (higher priority, more frequent)."""
    logger.info("Starting mistake fare sweep")
    job_run = await _start_job_run("mistake_sweep")

    try:
        deals_detected = 0
        alerts_sent = 0

        async with AsyncSessionLocal() as session:
            # Mistake fares are fastest-moving and most valuable, so we sweep
            # every home-airport x destination pair (not a hardcoded "popular"
            # list that ignores the user's actual home airport).
            for origin in config.app.home_airports:
                for destination in config.app.destinations:
                    # Check next 30 days daily
                    for day_offset in range(0, 30):
                        departure_date = (
                            datetime.utcnow() + timedelta(days=day_offset)
                        ).strftime("%Y-%m-%d")

                        deals = await _scan_route(
                            session,
                            origin,
                            destination,
                            departure_date,
                        )

                        for deal in deals:
                            if deal.deal_type == "mistake_fare":
                                deals_detected += 1
                                d, a = await _send_deal_alert(session, deal)
                                alerts_sent += a

        await _complete_job_run(job_run, deals_detected, alerts_sent)
        logger.info(
            f"Mistake fare sweep complete: {deals_detected} deals, {alerts_sent} alerts"
        )

    except Exception as e:
        logger.error(f"Mistake fare sweep failed: {e}")
        await telegram_bot.send_error_alert(f"Mistake fare sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def run_long_weekend_sweep() -> None:
    """Scan for long weekend deals (Thu→Sun, Fri→Mon)."""
    logger.info("Starting long weekend sweep")
    job_run = await _start_job_run("long_weekend_sweep")

    try:
        deals_detected = 0
        alerts_sent = 0

        date_pairs = get_long_weekend_date_pairs(
            config.app.long_weekend.look_ahead_months
        )

        async with AsyncSessionLocal() as session:
            for origin in config.app.home_airports:
                for destination in config.app.destinations:
                    for departure_date, return_date in date_pairs:
                        deals = await _scan_route(
                            session,
                            origin,
                            destination,
                            departure_date,
                            return_date=return_date,
                            route_suffix="-long-weekend",
                        )

                        for deal in deals:
                            deals_detected += 1
                            _, a = await _send_deal_alert(session, deal)
                            alerts_sent += a

        await _complete_job_run(job_run, deals_detected, alerts_sent)
        logger.info(
            f"Long weekend sweep complete: {deals_detected} deals, "
            f"{alerts_sent} alerts"
        )

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
