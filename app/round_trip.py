"""Lazy round-trip enrichment for confirmed one-way deals.

Round-trip fares only exist on paid providers (SearchAPI/Amadeus/Duffel). This
module is invoked ONCE per confirmed one-way deal (from ``_send_deal_alert``),
never inside the free sweep. It is best-effort: any failure, timeout, or quota
exhaustion falls back to a clearly-derived estimate rather than crashing the
alert. RT prices never feed deal detection or the one-way baseline.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.api.amadeus import AmadeusClient
from app.api.duffel import DuffelClient
from app.api.searchapi import SearchAPIClient
from app.cache import TTLCache
from app.config import config
from app.models.flight import FlightDeal
from app.utils.price_analysis import record_price_observations
from app.utils.rate_limiter import acquire_rt_slot

logger = logging.getLogger(__name__)

RT_PROVIDER_ORDER = [SearchAPIClient, AmadeusClient, DuffelClient]

rt_cache = TTLCache(ttl_seconds=max(1, config.app.rt_cache_ttl_hours) * 3600)


def _source_name(client_cls) -> str:
    return {
        SearchAPIClient: "SearchAPI",
        AmadeusClient: "Amadeus",
        DuffelClient: "Duffel",
    }.get(client_cls, getattr(client_cls, "__name__", "unknown"))


def _pick_return_date(deal: FlightDeal) -> str:
    base = datetime.strptime(deal.departure_date, "%Y-%m-%d")
    return (base + timedelta(days=config.app.rt_return_offset_days)).strftime("%Y-%m-%d")


def _derived_estimate(one_way: float) -> float:
    """Clearly-labeled fallback: roughly 2x one-way. Never a real quote."""
    return round(one_way * 2.0, 2)


def _suppress_if_phantom(deal: FlightDeal, rt_price: float) -> None:
    per_leg = rt_price / 2.0
    if per_leg < deal.current_price_usd:
        deal.rt_is_phantom = True


async def _lookup_rt(
    deal: FlightDeal, return_date: str
) -> tuple[float, str, list[dict]]:
    """Fetch a real round-trip price from the first working paid provider."""
    last_err: Exception | None = None
    for client_cls in RT_PROVIDER_ORDER:
        try:
            client = client_cls()
            flights = await client.search_flights(
                deal.origin,
                deal.destination,
                deal.departure_date,
                config.app.max_results_per_route,
                return_date,
            )
            if flights:
                price = min(client.get_flight_price(f) for f in flights)
                return price, _source_name(client_cls), flights
        except Exception as e:  # try the next provider
            last_err = e
            logger.warning(f"{_source_name(client_cls)} RT lookup failed: {e}")
            continue
    raise last_err or RuntimeError("No round-trip provider returned data")


async def enrich_round_trip(deal: FlightDeal, session) -> None:
    """Enrich a confirmed one-way deal with a round-trip price (best-effort).

    No-op unless ``config.app.round_trip_enrichment`` is enabled. Never raises;
    on any problem it stores a derived estimate so the alert still goes out.
    """
    if not config.app.round_trip_enrichment:
        return

    return_date = _pick_return_date(deal)
    deal.rt_return_date = return_date

    if not acquire_rt_slot():
        deal.round_trip_price_usd = _derived_estimate(deal.current_price_usd)
        deal.rt_source = "derived_quota"
        return

    cache_key = f"{deal.origin}:{deal.destination}:{deal.departure_date}:{return_date}"
    cached = rt_cache.get(cache_key)
    if cached is not None:
        price, source = cached
        deal.round_trip_price_usd = price
        deal.rt_source = source
        return

    try:
        price, source, flights = await asyncio.wait_for(
            _lookup_rt(deal, return_date), timeout=30
        )
        deal.round_trip_price_usd = price
        deal.rt_source = source
        rt_cache.set(cache_key, (price, source))
        if flights:
            await record_price_observations(
                session,
                deal.origin,
                deal.destination,
                deal.departure_date,
                flights,
                trip_type="round_trip",
            )
        _suppress_if_phantom(deal, price)
    except Exception as e:
        logger.warning(f"RT enrichment failed for {deal.route_id}: {e}")
        deal.round_trip_price_usd = _derived_estimate(deal.current_price_usd)
        deal.rt_source = "derived_error"
