"""Fli CLI client for flight search via Google Flights.

Wrapper around the `fli` CLI (https://github.com/punitarani/fli) that parses
JSON output into structured flight data compatible with the scheduler jobs.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Path to the fli executable
FLI_BIN = Path("/root/.local/bin/fli")


def _run_fli(args: List[str], timeout: int = 90) -> dict:
    """Run a fli CLI command and return parsed JSON output.

    Args:
        args: Command-line arguments to pass to `fli` (after the subcommand).
        timeout: Seconds before aborting the subprocess.

    Returns:
        Parsed JSON response from `fli`.

    Raises:
        RuntimeError: If `fli` exits non-zero or output is not valid JSON.
    """
    cmd = [str(FLI_BIN)] + args + ["--format", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"fli timed out after {timeout}s: {' '.join(cmd)}") from e

    if result.returncode != 0:
        raise RuntimeError(
            f"fli exited {result.returncode}: {result.stderr.strip()}"
        )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"fli returned non-JSON output: {e}\nstdout: {result.stdout[:500]}"
        ) from e


class FliClient:
    """Fli CLI client — wraps `fli flights` and `fli dates`."""

    def __init__(self):
        if not FLI_BIN.exists():
            raise RuntimeError(
                f"fli not found at {FLI_BIN}. "
                "Install with: uv tool install 'git+https://github.com/punitarani/fli'"
            )

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        max_results: int = 10,
        cabin_class: str = "ECONOMY",
        stops: str = "ANY",
        *,
        return_date: Optional[str] = None,
        airlines: Optional[List[str]] = None,
    ) -> List[dict]:
        """Search for flights on a specific date.

        Returns a list of flight dicts compatible with scheduler_jobs.py
        extraction logic, e.g.:
            {
                "price": {"total": "312.00"},
                "validatingAirlineCodes": ["DL"],
                "itineraries": [{"segments": [{"flight": {"number": "1234"}}]}],
                "booking_url": "https://...",
            }

        Args:
            origin: Departure airport IATA code.
            destination: Arrival airport IATA code.
            departure_date: YYYY-MM-DD.
            max_results: Max number of results (passed as --all or limited by API).
            cabin_class: ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST.
            stops: ANY, 0 (non-stop), 1, 2+.
            return_date: Optional return date for round-trip.
            airlines: Optional list of airline IATA codes to filter.
        """
        args = [
            "flights",
            origin,
            destination,
            departure_date,
            "--class", cabin_class,
            "--stops", stops,
        ]

        if return_date:
            args += ["--return", return_date]

        if airlines:
            for airline in airlines:
                args += ["--airlines", airline]

        # Request all results and let the caller slice
        if max_results > 30:
            args.append("--all")

        data = _run_fli(args)

        if not data.get("success"):
            logger.warning(
                f"fli flights {origin}→{destination} on {departure_date} "
                f"returned success=false: {data}"
            )
            return []

        flights_raw = data.get("flights", [])
        booking_base = data.get("booking_url", "")

        # Normalise into the shape scheduler_jobs.py expects
        flights = []
        for f in flights_raw[:max_results]:
            normalised = self._normalise_flight(f, booking_base)
            if normalised:
                flights.append(normalised)

        logger.info(
            f"fli flights: {origin}→{destination} {departure_date} "
            f"→ {len(flights)} results"
        )
        return flights

    def _normalise_flight(self, f: dict, booking_base: str) -> Optional[dict]:
        """Transform a fli flight dict into the canonical shape."""
        try:
            legs = f.get("legs", [])
            # Extract the first leg's first segment's marketing carrier as airline
            airline_codes = []
            for leg in legs:
                for seg in leg.get("segments", []):
                    carrier = seg.get("carrier", {})
                    if carrier and carrier.get("iata"):
                        airline_codes.append(carrier["iata"])

            if not airline_codes:
                airline_codes = ["Unknown"]

            # Build fake itineraries/segments shape so scheduler_jobs.py
            # extraction logic works unchanged
            segments = []
            for leg in legs:
                for seg in leg.get("segments", []):
                    carrier = seg.get("carrier", {})
                    segments.append({
                        "flight": {"number": seg.get("flightNumber", "") or ""},
                        "carrier": carrier,
                    })

            itinerary = {"segments": segments} if segments else {"segments": []}

            return {
                "price": {"total": str(f.get("price", {}).get("amount", 0))},
                "currency": f.get("price", {}).get("currency", "USD"),
                "validatingAirlineCodes": airline_codes,
                "itineraries": [itinerary] if itinerary["segments"] else [],
                "booking_url": f.get("booking_url") or booking_base,
                # Extra fields fli provides (not in Amadeus shape but harmless)
                "duration": f.get("duration"),
                "stops": f.get("stops"),
                "departure_time": f.get("departure_time"),
                "arrival_time": f.get("arrival_time"),
            }
        except Exception as e:
            logger.warning(f"Failed to normalise fli flight: {e} | {f}")
            return None

    async def search_dates(
        self,
        origin: str,
        destination: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        duration: int = 3,
        cabin_class: str = "ECONOMY",
        stops: str = "ANY",
        *,
        round_trip: bool = False,
        airlines: Optional[List[str]] = None,
        sort_by_price: bool = True,
    ) -> List[dict]:
        """Find cheapest dates to fly between two airports.

        Returns a list of date dicts:
            [{
                "departure_date": "2026-06-22",
                "return_date": None,
                "price": 312.0,
                "currency": "USD",
                "booking_url": "https://...",
            }, ...]
        """
        args = [
            "dates",
            origin,
            destination,
            "--duration", str(duration),
            "--class", cabin_class,
            "--stops", stops,
        ]

        if from_date:
            args += ["--from", from_date]
        if to_date:
            args += ["--to", to_date]
        if round_trip:
            args.append("--round")
        if sort_by_price:
            args.append("--sort")
        if airlines:
            for airline in airlines:
                args += ["--airlines", airline]

        data = _run_fli(args)

        if not data.get("success"):
            logger.warning(
                f"fli dates {origin}→{destination} returned success=false: {data}"
            )
            return []

        dates = data.get("dates", [])
        logger.info(
            f"fli dates: {origin}→{destination} → {len(dates)} date options"
        )
        return dates

    async def search_airports(self, query: str, limit: int = 10) -> List[dict]:
        """Search for airports by city name, airport name, or IATA code.

        Returns:
            [{"code": "JFK", "name": "John F Kennedy...", "match_type": "city"}, ...]
        """
        args = ["airports", query, "--limit", str(limit), "--json"]
        data = _run_fli(args)

        # airports --json returns a list directly (not wrapped in dict)
        if isinstance(data, list):
            return data
        logger.warning(f"Unexpected airports output: {data}")
        return []