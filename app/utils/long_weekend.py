"""Long weekend date pair generation."""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Day-of-week constants (Monday=0, Sunday=6)
_LONG_WEEKEND_STARTS = {3, 4}  # Thursday=3, Friday=4


def get_long_weekend_date_pairs(
    look_ahead_months: int = 12,
) -> list[tuple[str, str]]:
    """Generate (departure, return) date pairs for long weekends.

    Returns pairs for:
    - Thursday → Sunday (4-day weekend)
    - Friday → Monday (4-day weekend)

    Scans from today up to look_ahead_months out.
    """
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today + timedelta(days=look_ahead_months * 30)
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    current = today
    while current <= cutoff:
        if current.weekday() in _LONG_WEEKEND_STARTS:
            ret = current + timedelta(days=3)
            if ret <= cutoff:
                key = f"{current.strftime('%Y-%m-%d')}:{ret.strftime('%Y-%m-%d')}"
                if key not in seen:
                    seen.add(key)
                    pairs.append((current.strftime("%Y-%m-%d"), ret.strftime("%Y-%m-%d")))
        current += timedelta(days=1)

    logger.info(
        f"Generated {len(pairs)} long weekend date pairs "
        f"({look_ahead_months} months ahead)"
    )
    return pairs
