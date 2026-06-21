"""Price analysis utilities."""

import hashlib
import logging
from datetime import datetime, timedelta

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
    prices: list[float] = [row[0] for row in result.all()]

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


def get_route_type(origin: str, destination: str) -> str:
    us_airports = {
        "JFK", "LGA", "EWR", "BOS", "PWM", "ONT", "SBA", "AUS", "MCI",
        "SFO", "LAX", "ORD", "SEA", "MIA", "ATL", "DEN", "PHX", "LAS",
        "IAD", "DCA", "PDX", "STL", "MSP", "DTW", "PHL", "CLT", "FLL",
        "TPA", "RDU", "BWI", "SJC", "OAK", "SAN", "SMF",
    }
    eu_airports = {"LHR", "LTN", "EDI", "DUB", "BCN", "OSL", "CDG", "FRA", "AMS", "MAD", "FCO", "MUC", "ZRH", "ARN", "CPH"}
    asia_airports = {"NRT", "HND", "ICN", "PVG", "PEK", "HKG", "SIN", "BKK"}
    latam_airports = {"SJO", "PLS", "CUN", "MEX", "BOG", "LIM", "SCL", "GRU", "GIG", "EZE"}

    origin_us = origin.startswith("K") or origin in us_airports
    dest_us = destination.startswith("K") or destination in us_airports
    origin_eu = origin in eu_airports
    dest_eu = destination in eu_airports

    if origin_us and dest_us:
        return "domestic"
    if origin_us and destination in eu_airports:
        return "transatlantic"
    if origin_us and destination in asia_airports:
        return "transpacific"
    if origin_us and destination in latam_airports:
        return "latin_america"
    if origin_eu and dest_eu:
        return "europe"
    if destination.startswith("K") or destination in us_airports:
        if origin in eu_airports:
            return "transatlantic"
        if origin in asia_airports:
            return "transpacific"
        if origin in latam_airports:
            return "latin_america"
    return "domestic"


def apply_route_multiplier(median_price: float, origin: str, destination: str) -> float:
    route_type = get_route_type(origin, destination)
    multiplier = getattr(config.app.route_multipliers, route_type, 1.0)
    return median_price * multiplier


def detect_deal(
    current_price: float,
    median_price: float,
    origin: str | None = None,
    destination: str | None = None,
) -> tuple[bool, str | None]:
    if current_price >= median_price:
        return False, None

    if origin is not None and destination is not None:
        median_price = apply_route_multiplier(median_price, origin, destination)

    price_drop_percent = (median_price - current_price) / median_price

    if price_drop_percent >= config.app.deal_thresholds.mistake_fare_percent:
        return True, "mistake_fare"
    if price_drop_percent >= config.app.deal_thresholds.deep_flash_percent:
        return True, "deep_flash"
    if price_drop_percent >= config.app.deal_thresholds.flash_sale_percent:
        return True, "flash_sale"
    return False, None


def calculate_price_drop(current_price: float, median_price: float) -> float:
    """Calculate price drop percentage."""
    if median_price == 0:
        return 0.0
    return ((median_price - current_price) / median_price) * 100
