"""Route scanner — scrape providers, detect deals, cache and record observations.

Extracted from scheduler_jobs.py as a pure mechanical refactor (no behavior
changes). _scan_route runs the fli → SearchAPI → Amadeus → Duffel fallback
chain, applies dedup + median-baseline detection, and returns the list of
FlightDeal rows already committed to the caller's session.
"""

import asyncio
import logging
from datetime import datetime
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.api import AmadeusClient, DuffelClient, SearchAPIClient
from app.cache import price_cache
from app.config import config
from app.models.flight import FlightDeal
from app.scrapers.fli_client import FLIClient
from app.utils.circuit_breaker import circuit_breaker
from app.utils.deduplication import is_flight_seen_recently, mark_flight_seen
from app.utils.price_analysis import (
    calculate_median_price,
    calculate_percentile_baseline,
    calculate_price_drop,
    detect_deal,
    detect_deal_learned,
    generate_route_id,
    record_price_observations,
)

logger = logging.getLogger(__name__)

# Hard ceiling on a single sync fli scrape so one wedged upstream can never
# stall the entire sweep loop (the rest of the app keeps "running" forever).
FLI_TIMEOUT_SECONDS = 30


def _extract_stopover_airports(flight: dict, destination: str) -> list[str]:
    """Extract intermediate airports from flight segments.

    Returns airport codes for stops between origin and destination.
    Assumes segments are ordered as returned by the API.
    """
    segments = flight.get("itineraries", [{}])[0].get("segments", [])
    if len(segments) <= 1:
        return []

    via_airports = []
    for seg in segments:
        arrival = seg.get("arrival_airport") or seg.get("flight", {}).get("arrival_airport", "")
        if arrival and arrival not in via_airports:
            via_airports.append(arrival)

    # Remove the final destination if it's included
    if via_airports and via_airports[-1] == destination:
        via_airports = via_airports[:-1]

    return via_airports


def _build_booking_url(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    airline: str = "",
) -> str:
    """Build a flight-search deep link that reliably pre-fills origin,
    destination and dates.

    Google Flights deprecated every query-string / path deep-link format
    (all ``q=`` and hand-rolled ``tfs=`` variants now 302 to ``/unsupported``),
    so we use Kayak's path-based format ``/flights/MCI-JFK/YYYY-MM-DD`` which
    still fills the fields and returns HTTP 200.

    The link always opens a ROUND-TRIP search when a return date is known so
    the user can compare against Google's round-trip fare in one tap.  The
    price we display is one-way (fli only returns one-way fares).
    """
    origin = origin.strip().upper()
    destination = destination.strip().upper()
    segments = f"/{origin}-{destination}/{departure_date}"
    if return_date:
        segments += f"/{return_date}"
    url = f"https://www.kayak.com/flights{segments}"
    if airline:
        url += f"?sort=price&a={quote(airline.strip().upper())}"
    return url


async def _scan_route(
    session: AsyncSession,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    route_suffix: str = "",
) -> list[FlightDeal]:
    """Scan a route for deals.

    Args:
        route_suffix: Optional suffix for route ID (e.g. "-long-weekend").
        return_date: Optional return date for round-trip searches.
    """
    deals = []

    cached_data = await price_cache.get_cached_route_data(
        origin, destination, departure_date, return_date, route_suffix
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
    fli_error = False
    try:
        fli_client = FLIClient()
        flights = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                fli_client.search_flights,
                origin,
                destination,
                departure_date,
                return_date,
                config.app.max_results_per_route,
            ),
            timeout=FLI_TIMEOUT_SECONDS,
        )
        if flights:
            logger.info(f"fli returned {len(flights)} flights (FREE)")
    except TimeoutError:
        fli_error = True
        logger.warning(
            f"fli search timed out after {FLI_TIMEOUT_SECONDS}s for "
            f"{origin}-{destination}-{departure_date}"
        )
    except Exception as e:
        fli_error = True
        logger.warning(f"fli search failed: {e}")

    # A genuine empty result ([]) means "no flights right now" and we still try
    # the paid providers so we don't miss a deal. A fli ERROR only escalates to
    # paid providers when the operator opts in via fallback_on_fli_error (default
    # off) — otherwise a flaky free source would silently burn paid quota.
    if not flights and (not fli_error or config.app.fallback_on_fli_error):
        if circuit_breaker.is_allowed("SearchAPI"):
            try:
                searchapi = SearchAPIClient()
                flights = await searchapi.search_flights(
                    origin, destination, departure_date, config.app.max_results_per_route
                )
                if flights:
                    logger.info(f"SearchAPI returned {len(flights)} flights")
                circuit_breaker.record_success("SearchAPI")
            except Exception as e:
                logger.warning(f"SearchAPI search failed: {e}")
                circuit_breaker.record_failure("SearchAPI")
        else:
            logger.warning("SearchAPI circuit breaker open, skipping")

        if not flights and circuit_breaker.is_allowed("Amadeus"):
            try:
                amadeus = AmadeusClient()
                flights = await amadeus.search_flights(
                    origin,
                    destination,
                    departure_date,
                    config.app.max_results_per_route,
                )
                if flights:
                    logger.info(f"Amadeus returned {len(flights)} flights")
                circuit_breaker.record_success("Amadeus")
            except Exception as e2:
                logger.warning(f"Amadeus search failed: {e2}")
                circuit_breaker.record_failure("Amadeus")

        if not flights and circuit_breaker.is_allowed("Duffel"):
            try:
                duffel = DuffelClient()
                flights = await duffel.search_flights(
                    origin,
                    destination,
                    departure_date,
                    config.app.max_results_per_route,
                )
                if flights:
                    logger.info(f"Duffel returned {len(flights)} flights")
                circuit_breaker.record_success("Duffel")
            except Exception as e3:
                logger.error(f"Duffel search also failed: {e3}")
                circuit_breaker.record_failure("Duffel")

        if not flights:
            return deals

    if not flights:
        return deals

    median_price = await calculate_median_price(
        session,
        origin,
        destination,
        config.app.look_back_days,
        min_samples=config.app.min_baseline_samples,
        trip_type="one_way",
    )

    percentiles = await calculate_percentile_baseline(
        session, origin, destination, departure_date,
        min_samples=config.app.min_baseline_samples,
    )

    seen_airlines: set[str] = set()

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
            booking_url = _build_booking_url(
                origin, destination, departure_date, return_date, airline
            )

            if price < config.app.min_price_usd:
                continue

            route_id = generate_route_id(
                origin, destination, departure_date, airline,
                suffix=route_suffix, trip_type="one_way",
            )

            if await is_flight_seen_recently(session, route_id):
                continue

            if airline in seen_airlines:
                continue
            seen_airlines.add(airline)

            # Cold-start guard: without enough accumulated observations there is
            # no real baseline, so we never flag the current batch as deals
            # (that would be a false-positive factory). Observations are still
            # recorded below so subsequent scans build a genuine baseline.
            if median_price is None and percentiles is None:
                continue

            # Learned percentile baseline takes priority when available.
            # Falls back to the old median-based detection when the route+month
            # has insufficient observations for percentiles.
            if percentiles is not None:
                is_deal, deal_type = detect_deal_learned(price, percentiles)
                baseline_price = percentiles.get(50, median_price or price)
            else:
                is_deal, deal_type = detect_deal(
                    price, median_price, origin, destination
                )
                baseline_price = median_price

            if is_deal:
                price_drop = calculate_price_drop(price, baseline_price)

                deal = FlightDeal(
                    route_id=route_id,
                    origin=origin,
                    destination=destination,
                    departure_date=departure_date,
                    airline=airline,
                    flight_numbers=flight_numbers,
                    original_price_usd=baseline_price,
                    current_price_usd=price,
                    price_drop_percent=price_drop,
                    deal_type=deal_type or "baseline",
                    booking_url=booking_url,
                    trip_type="one_way",
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
            origin, destination, departure_date, flights, return_date, route_suffix
        )
        try:
            lowest_price = min(
                float(f.get("price", {}).get("total", float("inf"))) for f in flights
            )
        except (ValueError, TypeError):
            lowest_price = 0.0
        logger.debug(
            f"Cached {len(flights)} flights for {origin}-{destination}-{departure_date}, lowest: ${lowest_price:.2f}"
        )

        # Accumulate every scraped price into the baseline (excluded from the
        # median used for THIS scan; feeds future scans).
        recorded = await record_price_observations(
            session, origin, destination, departure_date, flights,
            config.app.min_price_usd, trip_type="one_way",
        )
        if recorded:
            logger.info(
                f"Recorded {recorded} price observations for "
                f"{origin}->{destination}-{departure_date}"
            )

    return deals
