"""Deduplication utilities."""

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight import AlertHistory, FlightDeal

logger = logging.getLogger(__name__)


def generate_deal_hash(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str,
    price: float,
) -> str:
    """Generate hash for flight deal deduplication."""
    data = f"{origin}-{destination}-{departure_date}-{airline}-{price:.2f}"
    return hashlib.sha256(data.encode()).hexdigest()


async def mark_flight_seen(
    session: AsyncSession,
    flight_deal: FlightDeal,
) -> None:
    """Mark a flight as seen to prevent duplicate alerts."""
    flight_deal.expired_at = datetime.utcnow() + timedelta(hours=24)
    session.add(flight_deal)
    await session.commit()


# Max alert attempts before marking permanently failed (stops infinite retries)
MAX_ALERT_ATTEMPTS = 5


async def is_flight_seen_recently(
    session: AsyncSession,
    route_id: str,
    hours: int = 24,
) -> bool:
    """Check if a flight was seen in the last N hours.

    A deal is considered "seen" only if its most recent alert was
    successfully delivered. If the last alert failed (or no alert
    has been sent yet), the deal is re-eligible for the next sweep
    so transient delivery failures don't permanently suppress it.

    If a deal has failed MAX_ALERT_ATTEMPTS times without success,
    it is marked permanently failed and will not be retried.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = (
        select(FlightDeal)
        .where(FlightDeal.route_id == route_id)
        .where(FlightDeal.seen_at >= cutoff)
        .where(FlightDeal.expired_at > datetime.utcnow())
        .limit(1)
    )

    result = await session.execute(query)
    deal = result.scalar_one_or_none()
    if deal is None:
        return False

    # Check all AlertHistory rows for this deal to count failures.
    alert_query = (
        select(AlertHistory)
        .where(AlertHistory.flight_deal_id == deal.id)
        .order_by(AlertHistory.sent_at.desc())
    )
    alert_result = await session.execute(alert_query)
    alerts = alert_result.scalars().all()

    if not alerts:
        # No alert has been sent yet — retry.
        return False

    # Count failed attempts. If all alerts failed and we've hit the threshold,
    # mark as permanently failed to stop retry storms.
    failed_count = sum(1 for a in alerts if a.status != "sent")
    if failed_count >= MAX_ALERT_ATTEMPTS:
        logger.info(
            f"Deal {deal.id} has {failed_count} failed alert attempts; "
            "marking permanently failed, will not retry"
        )
        deal.expired_at = datetime.utcnow()
        session.add(deal)
        await session.commit()
        return True

    if all(a.status != "sent" for a in alerts):
        # Last alert failed or was rate-limited — retry.
        return False
    return True


async def cleanup_expired_deals(
    session: AsyncSession,
) -> int:
    """Clean up expired flight deals from database."""
    query = select(FlightDeal).where(FlightDeal.expired_at < datetime.utcnow())
    result = await session.execute(query)
    expired_deals = result.scalars().all()

    count = 0
    for deal in expired_deals:
        await session.delete(deal)
        count += 1

    await session.commit()
    logger.info(f"Cleaned up {count} expired flight deals")
    return count
