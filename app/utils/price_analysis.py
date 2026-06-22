"""Price analysis utilities."""

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.flight import FlightDeal

logger = logging.getLogger(__name__)


def generate_route_id(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str,
    suffix: str = "",
) -> str:
    """Generate unique route ID for deduplication.

    An optional suffix differentiates route types (e.g. "-long-weekend").
    """
    data = f"{origin}-{destination}-{departure_date}-{airline}{suffix}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


async def calculate_median_price(
    session: AsyncSession,
    origin: str,
    destination: str,
    days_back: int = 30,
) -> float | None:
    """Calculate median price for a route over the last N days.

    Returns None if no price history exists (caller should use current
    search results to establish a baseline instead of a hardcoded default).
    """
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
        logger.info(f"No price history for {origin}->{destination}, using search results as baseline")
        return None

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


async def get_price_history(
    session: AsyncSession,
    origin: str,
    destination: str,
    days: int = 90,
) -> dict:
    """Get price history for a route over the last N days."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (
        select(
            func.date(FlightDeal.seen_at).label("date"),
            func.avg(FlightDeal.original_price_usd).label("median_price"),
            func.min(FlightDeal.current_price_usd).label("lowest_price"),
            func.count().label("sample_count"),
        )
        .where(FlightDeal.origin == origin)
        .where(FlightDeal.destination == destination)
        .where(FlightDeal.seen_at >= cutoff)
        .group_by(func.date(FlightDeal.seen_at))
        .order_by(func.date(FlightDeal.seen_at))
    )

    result = await session.execute(query)
    rows = result.all()

    history = [
        {
            "date": str(row.date),
            "median_price": float(row.median_price),
            "lowest_price": float(row.lowest_price),
            "sample_count": row.sample_count,
        }
        for row in rows
    ]

    if not history:
        return {
            "route": f"{origin}-{destination}",
            "days": days,
            "data_points": 0,
            "history": [],
            "current_median": None,
            "trend": "flat",
            "trend_percent": 0.0,
        }

    current_median = history[-1]["median_price"]

    if len(history) < 2:
        return {
            "route": f"{origin}-{destination}",
            "days": days,
            "data_points": len(history),
            "history": history,
            "current_median": current_median,
            "trend": "flat",
            "trend_percent": 0.0,
        }

    midpoint = len(history) // 2
    first_half = history[:midpoint]
    second_half = history[midpoint:]

    older_avg = sum(d["median_price"] for d in first_half) / len(first_half)
    recent_avg = sum(d["median_price"] for d in second_half) / len(second_half)

    if older_avg == 0:
        trend_percent = 0.0
    else:
        trend_percent = ((recent_avg - older_avg) / older_avg) * 100

    if trend_percent > 5:
        trend = "up"
    elif trend_percent < -5:
        trend = "down"
    else:
        trend = "flat"

    return {
        "route": f"{origin}-{destination}",
        "days": days,
        "data_points": len(history),
        "history": history,
        "current_median": current_median,
        "trend": trend,
        "trend_percent": round(trend_percent, 2),
    }
