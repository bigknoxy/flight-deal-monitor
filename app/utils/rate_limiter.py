"""Global alert rate limiter.

The app fans alerts out to multiple notifiers (Telegram, email, Slack, Discord).
`max_alerts_per_hour` is a budget that must be shared ACROSS all notifiers, not
charged per-notifier. Each notifier previously kept its own counter, so a burst
could emit roughly ``max_alerts_per_hour * (number of notifiers)`` messages.

This module enforces the budget globally with a simple sliding window.
"""

import threading
import time

from app.config import config

_lock = threading.Lock()
_timestamps: list[float] = []


def acquire_alert_slot() -> bool:
    """Try to claim one alert slot for the current hour.

    Returns True if the alert may be sent, False if the global hourly budget
    is exhausted.
    """
    limit = config.app.max_alerts_per_hour
    if limit <= 0:
        return True

    now = time.monotonic()
    cutoff = now - 3600.0

    with _lock:
        # Drop timestamps older than one hour.
        while _timestamps and _timestamps[0] < cutoff:
            _timestamps.pop(0)

        if len(_timestamps) >= limit:
            return False

        _timestamps.append(now)
        return True


def alerts_remaining() -> int:
    """Number of alert slots left in the current hour."""
    limit = config.app.max_alerts_per_hour
    if limit <= 0:
        return -1

    now = time.monotonic()
    cutoff = now - 3600.0
    with _lock:
        while _timestamps and _timestamps[0] < cutoff:
            _timestamps.pop(0)
        return max(0, limit - len(_timestamps))


# Separate budget for round-trip enrichment lookups. RT enrichment is a paid
# operation and must not compete with the alert budget.
_rt_timestamps: list[float] = []


def acquire_rt_slot() -> bool:
    """Try to claim one round-trip lookup slot for the current hour.

    Returns True if a paid RT lookup may proceed, False if the RT hourly budget
    is exhausted (caller should then fall back to a derived estimate).
    """
    limit = config.app.max_rt_lookups_per_hour
    if limit <= 0:
        return True

    now = time.monotonic()
    cutoff = now - 3600.0

    with _lock:
        while _rt_timestamps and _rt_timestamps[0] < cutoff:
            _rt_timestamps.pop(0)

        if len(_rt_timestamps) >= limit:
            return False

        _rt_timestamps.append(now)
        return True


def rt_remaining() -> int:
    """Number of round-trip lookup slots left in the current hour."""
    limit = config.app.max_rt_lookups_per_hour
    if limit <= 0:
        return -1

    now = time.monotonic()
    cutoff = now - 3600.0
    with _lock:
        while _rt_timestamps and _rt_timestamps[0] < cutoff:
            _rt_timestamps.pop(0)
        return max(0, limit - len(_rt_timestamps))
