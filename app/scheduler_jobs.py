"""Scheduler job implementations."""

import json
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.alert import telegram_bot
from app.api import AmadeusClient, DuffelClient, FliClient
from app.config import config
from app.database import AsyncSessionLocal
from app.models.flight import AlertHistory, FlightDeal
from app.models.job import JobRun
from app.utils.deduplication import is_flight_seen_recently, mark_flight_seen
from app.utils.price_analysis import (
    calculate_median_price,
    calculate_price_drop,
    detect_deal,
    generate_route_id,
)

logger = logging.getLogger(__name__)

FLI_BIN = Path("/root/.local/bin/fli")


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
                    for day_offset in range(0, config.app.look_ahead_days, 7):  # Weekly checks
                        departure_date = (
                            datetime.now(UTC) + timedelta(days=day_offset)
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
                            telegram_message_id = await telegram_bot.send_alert(deal)

                            # Record alert
                            if telegram_message_id:
                                alerts_sent += 1
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

        await _complete_job_run(job_run, deals_detected, alerts_sent)
        logger.info(
            f"Regular sweep complete: {deals_detected} deals, {alerts_sent} alerts"
        )

    except Exception as e:
        logger.error(f"Regular sweep failed: {e}")
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
                        datetime.now(UTC) + timedelta(days=day_offset)
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
                            telegram_message_id = await telegram_bot.send_alert(deal)

                            if telegram_message_id:
                                alerts_sent += 1
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

        await _complete_job_run(job_run, deals_detected, alerts_sent)
        logger.info(
            f"Mistake fare sweep complete: {deals_detected} deals, {alerts_sent} alerts"
        )

    except Exception as e:
        logger.error(f"Mistake fare sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def _scan_route(
    session: AsyncSession,
    origin: str,
    destination: str,
    departure_date: str,
    amadeus_priority: bool = True,
) -> list[FlightDeal]:
    """Scan a route for deals."""
    deals = []
    route_id = generate_route_id(origin, destination, departure_date, "")

    # Check if already seen recently
    if await is_flight_seen_recently(session, route_id):
        return deals

    # Get median price
    median_price = await calculate_median_price(
        session, origin, destination, config.app.look_back_days
    )

    # Try Amadeus first, then Duffel, then fli
    flights = []
    try:
        amadeus = AmadeusClient()
        flights = await amadeus.search_flights(
            origin, destination, departure_date, config.app.max_results_per_route
        )
    except Exception as e:
        logger.warning(f"Amadeus search failed: {e}, trying Duffel")
        try:
            duffel = DuffelClient()
            flights = await duffel.search_flights(
                origin, destination, departure_date, config.app.max_results_per_route
            )
        except Exception as e2:
            logger.warning(f"Duffel search also failed: {e2}, trying fli")
            try:
                fli = FliClient()
                flights = await fli.search_flights(
                    origin, destination, departure_date, config.app.max_results_per_route
                )
            except Exception as e3:
                logger.error(f"fli search also failed: {e3}")
                return deals

    # Check each flight for deals
    for flight in flights:
        # Extract flight info (adapt based on API response format)
        try:
            airline = flight.get("validatingAirlineCodes", ["Unknown"])[0]
            flight_numbers = ",".join(
                [seg.get("flight", {}).get("number", "") for seg in flight.get("itineraries", [{}])[0].get("segments", [])]
            )
            price = float(flight.get("price", {}).get("total", 0))

            if price < config.app.min_price_usd:
                continue

            # Check if deal
            is_deal, deal_type = detect_deal(price, median_price)

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
                    booking_url="https://example.com/book",  # Replace with actual booking URL
                )

                session.add(deal)
                await session.commit()
                await session.refresh(deal)

                await mark_flight_seen(session, deal)
                deals.append(deal)

        except Exception as e:
            logger.warning(f"Failed to process flight: {e}")
            continue

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
    job_run.completed_at = datetime.now(UTC)
    job_run.duration_seconds = (
        (job_run.completed_at - job_run.started_at).total_seconds()
    )
    job_run.status = "success"
    job_run.deals_detected = deals_detected
    job_run.alerts_sent = alerts_sent

    async with AsyncSessionLocal() as session:
        session.add(job_run)
        await session.commit()


async def _fail_job_run(job_run: JobRun, error_message: str) -> None:
    """Fail a job run record."""
    job_run.completed_at = datetime.now(UTC)
    job_run.duration_seconds = (
        (job_run.completed_at - job_run.started_at).total_seconds()
    )
    job_run.status = "failed"
    job_run.error_message = error_message

    async with AsyncSessionLocal() as session:
        session.add(job_run)
        await session.commit()


async def run_fli_sweep() -> None:
    """Run fli-native flight deal sweep.

    Uses `fli dates` to efficiently find cheap departure dates across a range,
    then fetches detailed flight info for the cheapest dates with `fli flights`.
    Sends Telegram alerts for deals below configured thresholds.

    Routes are loaded from config/routes.yaml if it exists, otherwise falls back
    to home_airports × destinations from app config.
    """
    logger.info("Starting fli-native flight deal sweep")
    job_run = await _start_job_run("fli_sweep")

    try:
        routes = _load_routes()
        deals_detected = 0
        alerts_sent = 0
        checked = 0

        for origin, destination in routes:
            try:
                dates = await _find_cheap_dates_fli(origin, destination)
                for date_info in dates:
                    checked += 1
                    # Skip if already seen recently
                    route_id = generate_route_id(
                        origin, destination, date_info["departure_date"], ""
                    )
                    async with AsyncSessionLocal() as session:
                        if await is_flight_seen_recently(session, route_id):
                            continue

                    # Get median price for deal detection
                    async with AsyncSessionLocal() as session:
                        median_price = await calculate_median_price(
                            session, origin, destination, config.app.look_back_days
                        )

                    price = date_info["price"]
                    if price < config.app.min_price_usd:
                        continue

                    # Detect deal
                    is_deal, deal_type = detect_deal(price, median_price)
                    if not is_deal:
                        continue

                    price_drop = calculate_price_drop(price, median_price)
                    deal = FlightDeal(
                        route_id=route_id,
                        origin=origin,
                        destination=destination,
                        departure_date=date_info["departure_date"],
                        airline=date_info.get("airline", "Multiple"),
                        flight_numbers=date_info.get("flight_numbers", ""),
                        original_price_usd=median_price,
                        current_price_usd=price,
                        price_drop_percent=price_drop,
                        deal_type=deal_type,
                        booking_url=date_info.get(
                            "booking_url",
                            f"https://www.google.com/travel/flights?q="
                            f"Flights+from+{origin}+to+{destination}"
                        ),
                    )

                    async with AsyncSessionLocal() as session:
                        session.add(deal)
                        await session.commit()
                        await session.refresh(deal)
                        await mark_flight_seen(session, deal)

                    deals_detected += 1
                    telegram_message_id = await telegram_bot.send_alert(deal)

                    async with AsyncSessionLocal() as session:
                        alert = AlertHistory(
                            flight_deal_id=deal.id,
                            telegram_message_id=telegram_message_id or None,
                            status="sent" if telegram_message_id else "failed",
                            error_message=(
                                None if telegram_message_id
                                else "Failed to send Telegram alert"
                            ),
                        )
                        session.add(alert)
                        await session.commit()

                    if telegram_message_id:
                        alerts_sent += 1

            except Exception as e:
                logger.warning(f"Failed to scan route {origin}→{destination}: {e}")
                continue

        await _complete_job_run(job_run, deals_detected, alerts_sent)
        logger.info(
            f"fli sweep complete: checked {checked} dates, "
            f"{deals_detected} deals, {alerts_sent} alerts"
        )

    except Exception as e:
        logger.error(f"fli sweep failed: {e}")
        await _fail_job_run(job_run, str(e))


async def _find_cheap_dates_fli(
    origin: str,
    destination: str,
    days_ahead: int = 60,
) -> list[dict]:
    """Find cheap dates for a route using `fli dates`.

    Returns dates sorted by price (lowest first), up to 30 results.
    """
    from_date = datetime.now(UTC).strftime("%Y-%m-%d")
    to_date = (datetime.now(UTC) + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    if not FLI_BIN.exists():
        logger.warning(f"fli not found at {FLI_BIN}, skipping {origin}→{destination}")
        return []

    try:
        result = subprocess.run(
            [
                str(FLI_BIN), "dates", origin, destination,
                "--from", from_date,
                "--to", to_date,
                "--sort",
                "--format", "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"fli dates timed out for {origin}→{destination}")
        return []

    if result.returncode != 0:
        logger.warning(f"fli dates failed for {origin}→{destination}: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    dates = data.get("dates", []) or []
    # Take top 30 cheapest dates
    return dates[:30]


def _load_routes() -> list[tuple]:
    """Load route pairs from config/routes.yaml, or fall back to config."""
    routes_path = Path("config/routes.yaml")
    if routes_path.exists():
        with open(routes_path) as f:
            data = yaml.safe_load(f) or {}
        routes = data.get("routes", [])
        if routes:
            return [(r["origin"], r["destination"]) for r in routes]

    # Fall back to cross-product of home_airports × destinations
    routes = []
    for origin in config.app.home_airports:
        for destination in config.app.destinations:
            if origin != destination:
                routes.append((origin, destination))
    return routes
