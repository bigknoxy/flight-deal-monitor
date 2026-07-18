"""Price analysis utilities."""

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.flight import FlightDeal, PriceObservation

# Booking-window buckets: days between "now" and departure when the price was
# observed / searched. A 2-day-out fare should not inform a 60-day-out baseline.
BOOKING_WINDOW_BUCKETS = ("0-7d", "8-21d", "22-60d", "61+d")


def booking_window_bucket(days_until: int) -> str:
    """Map days-until-departure to a coarse booking-window bucket."""
    if days_until <= 7:
        return "0-7d"
    if days_until <= 21:
        return "8-21d"
    if days_until <= 60:
        return "22-60d"
    return "61+d"


logger = logging.getLogger(__name__)


def generate_route_id(
    origin: str,
    destination: str,
    departure_date: str,
    airline: str,
    suffix: str = "",
    trip_type: str = "one_way",
) -> str:
    """Generate unique route ID for deduplication.

    An optional suffix differentiates route types (e.g. "-long-weekend").
    ``trip_type`` ensures one-way and round-trip never collide in the dedup key.
    """
    data = f"{origin}-{destination}-{departure_date}-{airline}-{trip_type}{suffix}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


async def calculate_median_price(
    session: AsyncSession,
    origin: str,
    destination: str,
    days_back: int = 30,
    min_samples: int = 5,
    trip_type: str = "one_way",
) -> float | None:
    """Calculate median price for a route from accumulated price observations.

    Returns None when there are fewer than ``min_samples`` observations in the
    window — i.e. the route is in cold-start and has no real baseline yet, so
    callers should NOT treat the current batch as deals.
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    query = (
        select(PriceObservation.price_usd)
        .where(PriceObservation.origin == origin)
        .where(PriceObservation.destination == destination)
        .where(PriceObservation.observed_at >= cutoff)
        .where(PriceObservation.trip_type == trip_type)
    )

    result = await session.execute(query)
    prices: list[float] = [row[0] for row in result.all()]

    if len(prices) < min_samples:
        logger.info(
            f"Insufficient baseline for {origin}->{destination}: "
            f"{len(prices)}/{min_samples} samples; treating as cold-start"
        )
        return None

    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    if n % 2 == 0:
        median = (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
    else:
        median = sorted_prices[n // 2]

    logger.info(f"Median price for {origin}->{destination}: ${median:.2f} (n={n})")
    return median


async def record_price_observations(
    session: AsyncSession,
    origin: str,
    destination: str,
    departure_date: str,
    flights: list[dict],
    min_price_usd: float = 0.0,
    trip_type: str = "one_way",
) -> int:
    """Persist every scraped price so a real baseline can accumulate.

    Returns the number of observations recorded. These feed
    ``calculate_median_price`` on subsequent scans (the current batch is
    intentionally NOT included in the median computed for this same scan).
    """
    from datetime import datetime

    try:
        dep_dt = datetime.strptime(departure_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        dep_dt = None

    rows: list[PriceObservation] = []
    for flight in flights:
        try:
            price = float(flight.get("price", {}).get("total", 0))
        except (TypeError, ValueError):
            continue
        if price <= 0 or price < min_price_usd:
            continue
        airline = flight.get("validatingAirlineCodes", ["Unknown"])[0]

        obs = PriceObservation(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            airline=airline,
            price_usd=price,
            trip_type=trip_type,
        )

        if dep_dt is not None:
            now = datetime.utcnow()
            days_until = (dep_dt - now).days
            obs.days_until_departure = days_until
            obs.departure_month = dep_dt.month
            obs.departure_day_of_week = dep_dt.weekday()
            obs.observed_at_month = now.month
            obs.observed_at_day_of_week = now.weekday()
            obs.booking_window_bucket = booking_window_bucket(days_until)

        rows.append(obs)

    if rows:
        session.add_all(rows)
        await session.commit()
    return len(rows)


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


async def calculate_percentile_baseline(
    session: AsyncSession,
    origin: str,
    destination: str,
    departure_date: str,
    min_samples: int = 5,
    booking_window_bucket: str | None = None,
) -> dict[int, float] | None:
    """Calculate percentile-based price thresholds for a route+departure-month.

    Uses accumulated PriceObservation rows. Returns a dict mapping percentile
    (5, 10, 20, 30, 50) to the price at that percentile, or None when there
    are fewer than ``min_samples`` observations for this route+month.

    When ``booking_window_bucket`` is provided the baseline is scoped to the
    same booking window as the current search, so a 2-day-out fare does not
    skew a 60-day-out baseline.
    """
    try:
        dep_dt = datetime.strptime(departure_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    month = dep_dt.month

    query = (
        select(PriceObservation.price_usd)
        .where(PriceObservation.origin == origin)
        .where(PriceObservation.destination == destination)
        .where(PriceObservation.departure_month == month)
    )
    if booking_window_bucket is not None:
        query = query.where(PriceObservation.booking_window_bucket == booking_window_bucket)
    query = query.order_by(PriceObservation.price_usd)

    result = await session.execute(query)
    prices: list[float] = [row[0] for row in result.all()]

    if len(prices) < min_samples:
        logger.info(
            f"Insufficient percentile baseline for {origin}->{destination} "
            f"month={month}: {len(prices)}/{min_samples} samples"
        )
        return None

    n = len(prices)
    percentiles: dict[int, float] = {}
    for pct in (5, 10, 20, 30, 50):
        idx = max(0, min(n - 1, int(n * pct / 100)))
        percentiles[pct] = prices[idx]

    logger.info(
        f"Percentile baseline for {origin}->{destination} month={month}"
        f"{' bucket=' + booking_window_bucket if booking_window_bucket else ''}: "
        f"P50=${percentiles[50]:.2f} P20=${percentiles[20]:.2f} "
        f"P10=${percentiles[10]:.2f} (n={n})"
    )
    return percentiles


def detect_deal_learned(
    current_price: float,
    percentiles: dict[int, float],
) -> tuple[bool, str | None]:
    """Detect deal using learned percentile thresholds.

    A price at or below the 20th percentile is a mistake fare,
    at or below the 30th is a deep flash, and at or below the 50th
    is a flash sale. This adapts to each route+month's natural price
    distribution without hardcoded percentage thresholds.
    """
    p50 = percentiles.get(50)
    if p50 is None or current_price >= p50:
        return False, None

    p20 = percentiles.get(20)
    p30 = percentiles.get(30)

    if p20 is not None and current_price <= p20:
        return True, "mistake_fare"
    if p30 is not None and current_price <= p30:
        return True, "deep_flash"
    return True, "flash_sale"


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
