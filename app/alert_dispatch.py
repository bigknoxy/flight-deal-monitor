"""Alert fan-out dispatcher — send a deal alert to every configured notifier.

Extracted from scheduler_jobs.py as a pure mechanical refactor (no behavior
changes). The fan-out runs all notifiers in parallel via asyncio.gather with
return_exceptions=True so a single notifier failure never aborts the sweep.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.alert import telegram_bot
from app.config import config
from app.models.flight import AlertHistory, FlightDeal
from app.notifiers.discord import discord_notifier
from app.notifiers.email import email_notifier
from app.notifiers.slack import slack_notifier
from app.round_trip import enrich_round_trip
from app.utils.rate_limiter import acquire_alert_slot

logger = logging.getLogger(__name__)


async def _send_deal_alert(
    session: AsyncSession,
    deal: FlightDeal,
) -> tuple[int, int]:
    """Send alerts to all configured notifiers and record in AlertHistory.

    Returns (deals_detected, alerts_sent) counts.
    """
    # Global hourly budget is shared across ALL notifiers. Skip the whole
    # fan-out if we've already spent it (per-notifier counters stay as a
    # secondary guard, but this is authoritative).
    if not acquire_alert_slot():
        logger.warning(
            "Global hourly alert budget exhausted; skipping alert for "
            f"{deal.route_id}"
        )
        alert = AlertHistory(
            flight_deal_id=deal.id,
            status="rate_limited",
            error_message="Global alert budget exhausted",
        )
        session.add(alert)
        await session.commit()
        return 1, 0

    # Best-effort round-trip enrichment (Tier 2). Only when we're actually
    # going to send, to avoid spending paid quota on rate-limited skips.
    if config.app.round_trip_enrichment:
        try:
            await enrich_round_trip(deal, session)
            await session.commit()
        except Exception as e:
            logger.warning(f"RT enrichment failed for {deal.route_id}: {e}")

    telegram_result, email_result, slack_result, discord_result = await asyncio.gather(
        telegram_bot.send_alert(deal),
        email_notifier.send_alert(deal),
        slack_notifier.send_alert(deal),
        discord_notifier.send_alert(deal),
        return_exceptions=True,
    )

    if isinstance(email_result, Exception):
        logger.warning(f"Email alert failed: {email_result}")
    elif email_result:
        logger.info(f"Email alert sent for {deal.route_id}")

    for name, result in [("slack", slack_result), ("discord", discord_result)]:
        if isinstance(result, BaseException):
            logger.error(f"{name} notifier failed: {result}")
        elif result is None:
            logger.warning(f"{name} notifier skipped (rate-limited or not configured)")

    telegram_message_id = telegram_result if isinstance(telegram_result, str) else None

    # Delivery is "sent" if ANY configured notifier succeeded, not just
    # Telegram. Previously a Slack-only setup would be mislabeled "failed".
    delivered_any = bool(telegram_message_id)
    for result in (email_result, slack_result, discord_result):
        if isinstance(result, str):
            delivered_any = True
            break

    alert = AlertHistory(
        flight_deal_id=deal.id,
        telegram_message_id=telegram_message_id,
        status="sent" if delivered_any else "failed",
        error_message=None
        if delivered_any
        else "No configured notifier delivered the alert",
    )

    session.add(alert)
    await session.commit()

    return 1, 1 if delivered_any else 0
