"""Scheduler job implementations."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.alert import telegram_bot
from app.api import AmadeusClient, DuffelClient, SearchAPIClient
from app.cache import price_cache
from app.config import config
from app.database import AsyncSessionLocal
from app.models.flight import AlertHistory, FlightDeal
from app.models.job import JobRun
from app.scrapers.fli_client import FLIClient
from app.utils.deduplication import (
    cleanup_expired_deals,
    is_flight_seen_recently,
    mark_flight_seen,
)
from app.utils.long_weekend import get_long_weekend_date_pairs
from app.utils.price_analysis import (
    calculate_median_price,
    calculate_price_drop,
    detect_deal,
    generate_route_id,
)

logger = logging.getLogger(__name__)


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
                            amadeus_priority=True,
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
            # Focus on high-volume routes for mistake fares
            popular_routes = [
                ("JFK", "LHR"),
                ("LAX", "NRT"),
                ("SFO", "SYD"),
                ("ORD", "DXB"),
            ]

            for origin, destination in popular_routes:
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
                        amadeus_priority=True,
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


async def _send_deal_alert(
    session: AsyncSession,
    deal: FlightDeal,
) -> tuple[int, int]:
    """Send a Telegram alert for a deal and record it in AlertHistory.

    Returns (deals_detected, alerts_sent) counts.
    """
    telegram_message_id = await telegram_bot.send_alert(deal)

    if telegram_message_id:
        alert = AlertHistory(
            flight_deal_id=deal.id,
            telegram_message_id=telegram_message_id,
            status="sent",
        )
    else:
        alert = AlertHistory(
            flight_deal_id=deal.id,
            status="failed",
            error_message="Failed to send Telegram alert",
        )

    session.add(alert)
    await session.commit()

    return 1, 1 if telegram_message_id else 0


async def _scan_route(
    session: AsyncSession,
    origin: str,
    destination: str,
    departure_date: str,
    amadeus_priority: bool = True,
    return_date: str | None = None,
    route_suffix: str = "",
) -> list[FlightDeal]:
    """Scan a route for deals.

    Args:
        route_suffix: Optional suffix for route ID (e.g. "-long-weekend").
        return_date: Optional return date for round-trip searches.
    """
    deals = []
    route_id = generate_route_id(
        origin, destination, departure_date, "", suffix=route_suffix
    )

    if await is_flight_seen_recently(session, route_id):
        return deals

    median_price = await calculate_median_price(
        session, origin, destination, config.app.look_back_days
    )

    cached_data = await price_cache.get_cached_route_data(
        origin, destination, departure_date
    )
    if cached_data is not None:
        _, seen_at = cached_data
        age_minutes = (datetime.utcnow() - seen_at).total_seconds() / 60
        if age_minutes < config.app.cache_ttl_minutes:
            logger.info(
                f"Skipping search for {origin}-{destination}-{departure_date}: "
                f"recently searched ({age_minutes:.0f} min ago)"
            )
            return deals

    flights = []
    try:
        # Try fli first (FREE - Google Flights via curl_cffi)
        fli_client = FLIClient()
        flights = await asyncio.get_event_loop().run_in_executor(
            None,
            fli_client.search_flights,
            origin,
            destination,
            departure_date,
            return_date,
            config.app.max_results_per_route,
        )
        if flights:
            logger.info(f"fli returned {len(flights)} flights (FREE)")
    except Exception as e:
        logger.warning(f"fli search failed: {e}")

    if not flights:
        try:
            # SearchAPI ($4/1K)
            searchapi = SearchAPIClient()
            flights = await searchapi.search_flights(
                origin, destination, departure_date, config.app.max_results_per_route
            )
            if flights:
                logger.info(f"SearchAPI returned {len(flights)} flights")
        except Exception as e:
            logger.warning(f"SearchAPI search failed: {e}")
            try:
                amadeus = AmadeusClient()
                flights = await amadeus.search_flights(
                    origin,
                    destination,
                    departure_date,
                    config.app.max_results_per_route,
                )
            except Exception as e2:
                logger.warning(f"Amadeus search failed: {e2}")
                try:
                    duffel = DuffelClient()
                    flights = await duffel.search_flights(
                        origin,
                        destination,
                        departure_date,
                        config.app.max_results_per_route,
                    )
                except Exception as e3:
                    logger.error(f"Duffel search also failed: {e3}")
                    return deals

    # Check each flight for deals
    for flight in flights:
        try:
            airline = flight.get("validatingAirlineCodes", ["Unknown"])[0]
            flight_numbers = ",".join(
                [
                    seg.get("flight", {}).get("number", "")
                    for seg in flight.get("itineraries", [{}])[0].get("segments", [])
                ]
            )
            price = float(flight.get("price", {}).get("total", 0))
            booking_url = flight.get(
                "booking_url", "https://www.google.com/travel/flights"
            )

            if price < config.app.min_price_usd:
                continue

            is_deal, deal_type = detect_deal(price, median_price, origin, destination)

            if is_deal:
                price_drop = calculate_price_drop(price, median_price)

                deal = FlightDeal(
                    route_id=route_id,
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    airline=airline,
                    flight_numbers=flight_numbers,
                    original_price_usd=median_price,
                    current_price_usd=price,
                    price_drop_percent=price_drop,
                    deal_type=deal_type,
                    booking_url=booking_url,
                )

                session.add(deal)
                await session.commit()
                await session.refresh(deal)

                await mark_flight_seen(session, deal)
                deals.append(deal)

        except Exception as e:
            logger.warning(f"Failed to process flight: {e}")
            continue

    if flights:
        await price_cache.set_cached_route_data(
            origin, destination, departure_date, flights
        )
        try:
            lowest_price = min(
                float(f.get("price", {}).get("total", float("inf")))
                for f in flights
            )
        except (ValueError, TypeError):
            lowest_price = 0.0
        logger.debug(
            f"Cached {len(flights)} flights for {origin}-{destination}-{departure_date}, lowest: ${lowest_price:.2f}"
        )

    return deals


async def _start_job_run(job_id: str) -> JobRun:
    """Start a job run record."""
    async with AsyncSessionLocal() as session:
        job_run = JobRun(job_id=job_id)
        session.add(job_run)
        await session.commit()
        await session.refresh(job_run)
        return job_run


async def _complete_job_run(
    job_run: JobRun,
    deals_detected: int,
    alerts_sent: int,
) -> None:
    """Complete a job run record."""
    job_run.completed_at = datetime.utcnow()
    job_run.duration_seconds = (
        job_run.completed_at - job_run.started_at
    ).total_seconds()
    job_run.status = "success"
    job_run.deals_detected = deals_detected
    job_run.alerts_sent = alerts_sent

    async with AsyncSessionLocal() as session:
        session.add(job_run)
        await session.commit()


async def _fail_job_run(job_run: JobRun, error_message: str) -> None:
    """Fail a job run record."""
    job_run.completed_at = datetime.utcnow()
    job_run.duration_seconds = (
        job_run.completed_at - job_run.started_at
    ).total_seconds()
    job_run.status = "failed"
    job_run.error_message = error_message

    async with AsyncSessionLocal() as session:
        session.add(job_run)
        await session.commit()


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
                            amadeus_priority=True,
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
