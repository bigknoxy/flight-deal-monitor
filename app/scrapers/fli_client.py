"""Wrapper around the fli library for flight search."""

import json
import logging
import os
import subprocess
import sys
from typing import Any

logger = logging.getLogger(__name__)


# Raised when fli cannot produce results for a route (library error, network,
# or invalid airport codes). Callers distinguish this from a genuine "no
# flights" empty result so they don't waste paid fallback quota.
class FLISearchError(Exception):
    """fli search failed to return results."""


def _ensure_fli_importable() -> None:
    """Make the fli package importable in this process.

    fli is installed under a pipx venv rather than the app env. Prefer the
    ``FLI_SITE_PACKAGES`` env override, then fall back to the original
    machine-specific pipx path. Imported lazily so the parent (monitor)
    process never needs fli installed — only the search subprocess does.
    """
    fli_site_packages = os.environ.get("FLI_SITE_PACKAGES", "")
    if fli_site_packages and fli_site_packages not in sys.path:
        sys.path.insert(0, fli_site_packages)

    try:
        from fli.models import (  # noqa: F401
            Airport,
            FlightSearchFilters,
            FlightSegment,
            PassengerInfo,
        )
        from fli.search import SearchFlights  # noqa: F401
    except ImportError:
        sys.path.insert(
            0, "/root/.local/pipx/venvs/flights/lib/python3.11/site-packages"
        )
        from fli.models import (  # noqa: F401
            Airport,
            FlightSearchFilters,
            FlightSegment,
            PassengerInfo,
        )
        from fli.search import SearchFlights  # noqa: F401


def _run_fli_search(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str | None = None,
    max_results: int = 10,
    cabin_class: str = "ECONOMY",
    max_stops: str = "ANY",
) -> list[dict]:
    """Perform the actual fli search. Runs in a separate process so a wedged
    upstream call can be killed by a hard timeout instead of leaking a thread
    in the caller's executor pool forever.

    Returns an empty list for a genuine "no flights" result, and raises
    FLISearchError on any library/network failure.
    """
    _ensure_fli_importable()
    from fli.models import Airport, FlightSearchFilters, FlightSegment, PassengerInfo
    from fli.search import SearchFlights

    try:
        origin_airport = getattr(Airport, origin.upper(), None)
        dest_airport = getattr(Airport, destination.upper(), None)
        if not origin_airport or not dest_airport:
            logger.warning(f"Invalid airport codes: {origin}, {destination}")
            # Genuinely no results for these codes — not an error.
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

        searcher = SearchFlights()
        results = searcher.search(filters, top_n=max_results)

        if not results:
            return []

        flights = []
        for r in results:
            if isinstance(r, tuple):
                for segment in r:
                    flights.append(_to_dict(segment))
            else:
                flights.append(_to_dict(r))

        return flights[:max_results]

    except FLISearchError:
        raise
    except Exception as e:
        logger.warning(f"fli search failed: {e}")
        raise FLISearchError(str(e)) from e


def _to_dict(result: Any) -> dict:
    """Convert FlightResult to dictionary matching SearchAPI format."""
    leg = result.legs[0] if result.legs else None

    segment = {"flight": {"number": leg.flight_number} if leg else {}}

    return {
        "validatingAirlineCodes": [result.primary_airline_name],
        "itineraries": [{"segments": [segment]}],
        "price": {"total": f"{result.price:.2f}"},
        "type": "One way",
        "total_duration": result.duration,
        "booking_url": "",
    }


class FLIClient:
    """Client for interacting with the fli library.

    The synchronous fli search is executed in a short-lived subprocess with a
    hard timeout. This is the only way to truly cancel a wedged fli call:
    ``asyncio.wait_for`` on a ``run_in_executor`` future cancels the *await*,
    not the thread — so a hung fli call would otherwise leak an executor
    thread forever and eventually starve the whole sweep. A ``subprocess.run``
    timeout actually kills the child process (and its process group).
    """

    def __init__(self) -> None:
        self._module_path = os.path.abspath(__file__)

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        max_results: int = 10,
        cabin_class: str = "ECONOMY",
        max_stops: str = "ANY",
        timeout: int = 30,
    ) -> list[dict]:
        """Search for flights using fli, isolated in a subprocess.

        Returns an empty list for a genuine "no flights" result, and raises
        FLISearchError on any library/network failure or timeout.
        """
        args = [
            sys.executable,
            self._module_path,
            origin,
            destination,
            departure_date,
            return_date or "",
            str(max_results),
            cabin_class,
            max_stops,
        ]
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout + 10,
                start_new_session=True,
                env=os.environ,
            )
        except subprocess.TimeoutExpired as e:
            # Kill the whole process group so no orphaned fli children linger.
            # subprocess.TimeoutExpired exposes no .process attr; Best-effort
            # cleanup is guarded so a missing pid is a no-op.
            try:
                import signal

                pid = e.pid if hasattr(e, "pid") and e.pid else None
                if pid is not None:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            logger.warning(
                f"fli search timed out after {timeout}s for {origin}-{destination}"
            )
            raise FLISearchError(f"fli search timed out after {timeout}s") from e

        if proc.returncode != 0:
            logger.warning(
                f"fli subprocess failed ({proc.returncode}): {proc.stderr.strip()[:300]}"
            )
            raise FLISearchError(proc.stderr.strip() or "fli subprocess failed")

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            logger.warning(f"fli subprocess returned invalid JSON: {proc.stdout[:200]}")
            raise FLISearchError("invalid fli subprocess output") from e

        # A genuine empty result is `{"flights": []}`, not an error.
        return payload.get("flights", [])


if __name__ == "__main__":
    # Entry point used by FLIClient to run the search out-of-process.
    # argv: origin destination departure_date return_date max_results cabin max_stops
    _argv = sys.argv
    _origin = _argv[1] if len(_argv) > 1 else ""
    _dest = _argv[2] if len(_argv) > 2 else ""
    _date = _argv[3] if len(_argv) > 3 else ""
    _ret = _argv[4] if len(_argv) > 4 else ""
    _max = int(_argv[5]) if len(_argv) > 5 else 10
    _cabin = _argv[6] if len(_argv) > 6 else "ECONOMY"
    _stops = _argv[7] if len(_argv) > 7 else "ANY"

    try:
        _results = _run_fli_search(
            _origin,
            _dest,
            _date,
            _ret or None,
            _max,
            _cabin,
            _stops,
        )
    except FLISearchError as e:
        print(json.dumps({"flights": [], "error": str(e)}))
        sys.exit(1)

    print(json.dumps({"flights": _results}))
