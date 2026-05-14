"""Price analysis utilities."""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.flight import FlightDeal

logger = logging.getLogger(__name__)


def generate_route_id(
    origin: str, destination: str, departure_date: str, airline: str
) -> str:
    """Generate unique route ID for deduplication."""
    data = f"{origin}-{destination}-{departure_date}-{airline}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


async def calculate_median_price(
    session: AsyncSession,
    origin: str,
    destination: str,
    days_back: int = 30,
) -> float:
    """Calculate median price for a route over the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    query = (
        select(FlightDeal.original_price_usd)
        .where(FlightDeal.origin == origin)
        .where(FlightDeal.destination == destination)
        .where(FlightDeal.seen_at >= cutoff)
    )

    result = await session.execute(query)
    prices = [row[0] for row in result.all()]

    if not prices:
        logger.warning(f"No price history for {origin}->{destination}, using default")
        return 500.0  # Default fallback price

    # Calculate median
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    if n % 2 == 0:
        median = (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
    else:
        median = sorted_prices[n // 2]

    logger.info(f"Median price for {origin}->{destination}: ${median:.2f} (n={n})")
    return median


def detect_deal(
    current_price: float,
    median_price: float,
) -> Tuple[bool, Optional[str]]:
    """Detect if a flight is a deal based on price thresholds."""
    if current_price >= median_price:
        return False, None

    price_drop_percent = (median_price - current_price) / median_price

    # Mistake fare: <30% of median (more than 70% off)
    if current_price < median_price * config.app.mistake_fare_threshold:
        return True, "mistake_fare"

    # Flash sale: ≥40% below median
    if price_drop_percent >= config.app.flash_sale_threshold:
        return True, "flash_sale"

    return False, None


def calculate_price_drop(current_price: float, median_price: float) -> float:
    """Calculate price drop percentage."""
    if median_price == 0:
        return 0.0
    return ((median_price - current_price) / median_price) * 100