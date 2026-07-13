"""SearchAPI Google Flights client.

API docs: https://www.searchapi.io/docs/google-flights-api
"""

import logging
from typing import Any

import httpx

from app.config import config

logger = logging.getLogger(__name__)

SEARCHAPI_BASE_URL = "https://www.searchapi.io/api/v1/search"


class SearchAPIClient:
    """SearchAPI Google Flights client (no OAuth, simple API key auth)."""

    def __init__(self) -> None:
        self.api_key = config.env.searchapi_api_key
        self.base_url = SEARCHAPI_BASE_URL

    async def search_flights(
        self,
        departure_id: str,
        arrival_id: str,
        date: str,
        max_results: int = 10,
        return_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for flights using SearchAPI Google Flights API.

        Normalizes the response to match the format expected by
        the downstream deal-detection pipeline (same shape as Amadeus).
        Pass ``return_date`` to request round-trip fares.
        """
        params: dict[str, Any] = {
            "engine": "google_flights",
            "flight_type": "round_trip" if return_date else "one_way",
            "departure_id": departure_id,
            "arrival_id": arrival_id,
            "outbound_date": date,
            "api_key": self.api_key,
        }
        if return_date:
            params["return_date"] = return_date

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            result = response.json()

        # Combine best and other results for maximum coverage
        raw_flights = result.get("best_flights", []) + result.get("other_flights", [])

        normalized = [self._normalize_flight(f) for f in raw_flights[:max_results]]

        logger.info(
            f"Found {len(normalized)} flights from {departure_id} to {arrival_id}"
        )
        return normalized

    def _normalize_flight(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a SearchAPI flight itinerary to the standard normalized format."""
        segments_raw = raw.get("flights", [])
        # Empty flights list handled gracefully below
        if not segments_raw:
            segments_raw = []

        first = segments_raw[0] if segments_raw else {}
        airline = first.get("airline", "Unknown")

        normalized_segments: list[dict[str, Any]] = []
        for seg in segments_raw:
            flight_number = seg.get("flight_number", "") or ""
            normalized_segments.append(
                {"flight": {"number": flight_number.replace(" ", "")}}
            )

        # Price: raw value is in cents, convert to USD
        raw_price = raw.get("price", 0)
        if raw_price is None:
            raw_price = 0
        try:
            price_usd = float(raw_price) / 100.0
        except (TypeError, ValueError):
            price_usd = 0.0

        return {
            "validatingAirlineCodes": [airline],
            "itineraries": [{"segments": normalized_segments}],
            "price": {"total": f"{price_usd:.2f}"},
            "type": raw.get("type", "One way"),
            "total_duration": raw.get("total_duration", 0),
        }

    async def get_flight_price(self, flight: dict[str, Any]) -> float:
        """Extract price from normalized flight."""
        try:
            return float(flight["price"]["total"])
        except (KeyError, TypeError, ValueError):
            logger.warning(f"Could not extract price from flight: {flight}")
            return 0.0
