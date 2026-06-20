"""
Google Flights browser-based scraper for free flight data.
Uses curl with proper headers to mimic browser requests.
"""
import json


class GoogleFlightsBrowserScraper:
    """Scrape Google Flights using curl with browser headers."""

    def __init__(self):
        self.base_url = "https://www.google.com/_/FlightsFrontendUi/data/"
        self.session_cookie = None

    def search(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        max_results: int = 10,
    ) -> dict:
        """
        Search flights using curl-based approach.

        The fli library approach: encode the filter, POST to the RPC endpoint
        """
        try:
            # Use fli library directly since it has the encoding logic
            return self._search_with_fli(
                origin, destination, departure_date, return_date, max_results
            )
        except Exception as e:
            return {"flights": [], "total": 0, "error": str(e)}

    def _search_with_fli(self, origin, destination, dep_date, ret_date, max_results):
        """Use the installed fli package for encoding and request."""
        import sys

        sys.path.insert(
            0, "/root/.local/pipx/venvs/flights/lib/python3.11/site-packages"
        )

        from fli.core.builders import build_flight_segments
        from fli.models import (
            Airport,
            FlightSearchFilters,
            PassengerInfo,
        )
        from fli.search import SearchFlights

        try:
            # Build airport objects
            origin_airport = (
                Airport.from_code(origin)
                if len(origin) == 3
                else Airport.lookup(origin)
            )
            dest_airport = (
                Airport.from_code(destination)
                if len(destination) == 3
                else Airport.lookup(destination)
            )

            # Build segments
            segments, trip_type = build_flight_segments(
                origin_airport, dest_airport, dep_date, ret_date
            )

            # Create filters
            filters = FlightSearchFilters(
                passenger_info=PassengerInfo(adults=1),
                flight_segments=segments,
            )

            # Search
            search = SearchFlights()
            results = search.search(filters, top_n=max_results)

            if not results:
                return {"flights": [], "total": 0, "error": None}

            flights = []
            for r in results:
                if isinstance(r, tuple):
                    for segment in r:
                        flights.append(self._result_to_dict(segment))
                else:
                    flights.append(self._result_to_dict(r))

            return {
                "flights": flights[:max_results],
                "total": len(flights),
                "error": None,
            }

        except Exception as e:
            return {"flights": [], "total": 0, "error": str(e)}

    def _result_to_dict(self, result) -> dict:
        """Convert a FlightResult to a dictionary."""
        flight_data = {
            "airline": result.airline.name
            if hasattr(result.airline, "name")
            else str(result.airline),
            "flight_number": result.flight_number,
            "price": result.price,
            "currency": result.currency,
            "duration": result.duration_text,
        }

        if result.legs:
            leg = result.legs[0]
            flight_data["departure_time"] = (
                leg.departure_datetime.strftime("%H:%M")
                if hasattr(leg, "departure_datetime") and leg.departure_datetime
                else ""
            )
            flight_data["arrival_time"] = (
                leg.arrival_datetime.strftime("%H:%M")
                if hasattr(leg, "arrival_datetime") and leg.arrival_datetime
                else ""
            )

        return flight_data


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
) -> dict:
    """Convenience function to search flights."""
    scraper = GoogleFlightsBrowserScraper()
    return scraper.search(origin, destination, departure_date, return_date)


if __name__ == "__main__":
    result = search_flights("JFK", "LAX", "2026-07-15", "2026-07-22")
    print(json.dumps(result, indent=2))
