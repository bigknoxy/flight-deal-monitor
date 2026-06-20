"""Wrapper around the fli library for flight search."""
import logging
import sys
from typing import Any

try:
    from fli.models import Airport, FlightSearchFilters, FlightSegment, PassengerInfo
    from fli.search import SearchFlights
except ImportError:
    sys.path.insert(0, "/root/.local/pipx/venvs/flights/lib/python3.11/site-packages")
    from fli.models import Airport, FlightSearchFilters, FlightSegment, PassengerInfo
    from fli.search import SearchFlights

logger = logging.getLogger(__name__)


class FLIClient:
    """Client for interacting with the fli library."""

    def __init__(self) -> None:
        self.searcher = SearchFlights()

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        max_results: int = 10,
        cabin_class: str = "ECONOMY",
        max_stops: str = "ANY",
    ) -> list[dict]:
        """Search for flights using fli library.

        Note: Round trips currently disabled - Google returns None for multi-leg searches.
        Use one-way searches and combine if needed.
        """
        try:
            origin_airport = getattr(Airport, origin.upper(), None)
            dest_airport = getattr(Airport, destination.upper(), None)
            if not origin_airport or not dest_airport:
                logger.warning(f"Invalid airport codes: {origin}, {destination}")
                return []

            # Always do one-way search (fli has issues with round-trip)
            segments = [
                FlightSegment(
                    departure_airport=[[origin_airport, 0]],
                    arrival_airport=[[dest_airport, 0]],
                    travel_date=departure_date,
                )
            ]

            filters = FlightSearchFilters(
                passenger_info=PassengerInfo(adults=1),
                flight_segments=segments,
            )

            results = self.searcher.search(filters, top_n=max_results)

            if not results:
                return []

            flights = []
            for r in results:
                if isinstance(r, tuple):
                    for segment in r:
                        flights.append(self._to_dict(segment))
                else:
                    flights.append(self._to_dict(r))

            return flights[:max_results]

        except Exception as e:
            logger.warning(f"fli search failed: {e}")
            return []

    def _to_dict(self, result: Any) -> dict:
        """Convert FlightResult to dictionary matching SearchAPI format."""
        leg = result.legs[0] if result.legs else None

        segment = {"flight": {"number": leg.flight_number} if leg else {}}

        # Build booking URL from token
        booking_url = ""
        if result.booking_token:
            token = result.booking_token
            if token.startswith('["') and token.endswith('"]'):
                # Extract token string from JSON array
                try:
                    import json

                    token_data = json.loads(token)
                    actual_token = token_data[0] if token_data else None
                except json.JSONDecodeError:
                    actual_token = token
            else:
                actual_token = token

            if actual_token:
                # Clean up token for URL
                clean_token = (
                    actual_token.replace('"', "")
                    .replace("+", "")
                    .replace("/", "")
                    .replace("=", "")
                )
                booking_url = (
                    f"https://www.google.com/travel/flights?q={clean_token[:100]}"
                )

        return {
            "validatingAirlineCodes": [result.primary_airline_name],
            "itineraries": [{"segments": [segment]}],
            "price": {"total": f"{result.price:.2f}"},
            "type": "One way",
            "total_duration": result.duration,
            "booking_url": booking_url,
        }


if __name__ == "__main__":
    client = FLIClient()

    # Test one way
    print("=== One Way MCI -> LHR ===")
    flights = client.search_flights("MCI", "LHR", "2026-07-15")
    print(f"Found {len(flights)} flights")
    for f in flights[:3]:
        print(f)

    # Test round trip
    print("\n=== Round Trip MCI -> LHR ===")
    flights = client.search_flights("MCI", "LHR", "2026-07-15", "2026-07-22")
    print(f"Found {len(flights)} flights")
    for f in flights[:3]:
        print(f)
