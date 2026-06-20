"""Deduplication utilities."""

import hashlib
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flight import FlightDeal

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


async def is_flight_seen_recently(
    session: AsyncSession,
    route_id: str,
    hours: int = 24,
) -> bool:
    """Check if a flight was seen in the last N hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = (
        select(FlightDeal)
        .where(FlightDeal.route_id == route_id)
        .where(FlightDeal.seen_at >= cutoff)
        .where(FlightDeal.expired_at > datetime.utcnow())
        .limit(1)
    )

    result = await session.execute(query)
    return await result.scalar_one_or_none() is not None


async def cleanup_expired_deals(
    session: AsyncSession,
) -> int:
    """Clean up expired flight deals from database."""
    query = select(FlightDeal).where(FlightDeal.expired_at < datetime.utcnow())
    result = await session.execute(query)
    expired_deals = await result.scalars().all()

    count = 0
    for deal in expired_deals:
        await session.delete(deal)
        count += 1

    await session.commit()
    logger.info(f"Cleaned up {count} expired flight deals")
    return count