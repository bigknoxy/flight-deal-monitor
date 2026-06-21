"""Flexible dates and multi-city route generation."""

import logging
from datetime import datetime, timedelta
from itertools import permutations

logger = logging.getLogger(__name__)


def expand_date_range(target_date: str, range_days: int = 3) -> list[str]:
    """Return all dates in [target - range, target + range] as YYYY-MM-DD strings."""
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    start = dt - timedelta(days=range_days)
    end = dt + timedelta(days=range_days)
    dates: list[str] = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def generate_multi_city_routes(
    home: str, destinations: list[str], max_stops: int = 2
) -> list[tuple[str, str, str]]:
    """Generate (origin, stop, destination) combinations.

    Example: home=MCI, destinations=[LHR, BCN, DUB]
    Returns: [(MCI, LHR, BCN), (MCI, LHR, DUB), (MCI, BCN, DUB), ...]
    Only generates routes where stop != destination and both != home.
    """
    if max_stops < 2:
        return []

    routes: list[tuple[str, str, str]] = []
    for stop, dest in permutations(destinations, 2):
        if stop != dest and stop != home and dest != home:
            routes.append((home, stop, dest))
    return routes
