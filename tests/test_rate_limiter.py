"""Tests for the global alert + round-trip rate limiters.

These exercise the pure sliding-window logic by resetting the module-level
timestamp lists and monkeypatching ``config.app`` limits.
"""

import pytest

from app.config import config
from app.utils import rate_limiter


@pytest.fixture
def reset_windows(monkeypatch):
    """Clear both sliding windows and use a small limit for determinism."""
    rate_limiter._timestamps.clear()
    rate_limiter._rt_timestamps.clear()
    monkeypatch.setattr(config.app, "max_alerts_per_hour", 3)
    monkeypatch.setattr(config.app, "max_rt_lookups_per_hour", 2)
    yield
    rate_limiter._timestamps.clear()
    rate_limiter._rt_timestamps.clear()


class TestAlertLimiter:
    def test_acquire_until_exhausted(self, reset_windows):
        assert rate_limiter.acquire_alert_slot() is True
        assert rate_limiter.acquire_alert_slot() is True
        assert rate_limiter.acquire_alert_slot() is True
        # Budget of 3 exhausted.
        assert rate_limiter.acquire_alert_slot() is False

    def test_alerts_remaining_counts_down(self, reset_windows):
        assert rate_limiter.alerts_remaining() == 3
        rate_limiter.acquire_alert_slot()
        assert rate_limiter.alerts_remaining() == 2
        rate_limiter.acquire_alert_slot()
        rate_limiter.acquire_alert_slot()
        assert rate_limiter.alerts_remaining() == 0

    def test_negative_limit_means_unlimited(self, reset_windows):
        rate_limiter._timestamps.clear()
        # Patch limit to non-positive -> always allowed, remaining is -1.
        config.app.max_alerts_per_hour = 0
        assert rate_limiter.acquire_alert_slot() is True
        assert rate_limiter.alerts_remaining() == -1


class TestRTLimiter:
    def test_rt_acquire_until_exhausted(self, reset_windows):
        assert rate_limiter.acquire_rt_slot() is True
        assert rate_limiter.acquire_rt_slot() is True
        assert rate_limiter.acquire_rt_slot() is False

    def test_rt_remaining(self, reset_windows):
        assert rate_limiter.rt_remaining() == 2
        rate_limiter.acquire_rt_slot()
        assert rate_limiter.rt_remaining() == 1

    def test_rt_negative_limit_unlimited(self, reset_windows):
        rate_limiter._rt_timestamps.clear()
        config.app.max_rt_lookups_per_hour = -1
        assert rate_limiter.acquire_rt_slot() is True
        assert rate_limiter.rt_remaining() == -1


class TestLimiterIsolation:
    """Alert budget must not be charged against the RT budget and vice versa."""

    def test_budgets_independent(self, reset_windows):
        # Exhaust the alert budget (3 slots).
        for _ in range(3):
            assert rate_limiter.acquire_alert_slot() is True
        assert rate_limiter.acquire_alert_slot() is False
        # RT budget (2 slots) is untouched.
        assert rate_limiter.rt_remaining() == 2
        assert rate_limiter.acquire_rt_slot() is True


class TestSlidingWindowExpiry:
    """Old timestamps (>1h) must be dropped so the budget refills."""

    def test_expired_slots_freed(self, reset_windows, monkeypatch):
        clock = {"t": 1000.0}
        monkeypatch.setattr(
            rate_limiter.time, "monotonic", lambda: clock["t"]
        )

        # Fill the alert budget (3 slots) at t=1000.
        for _ in range(3):
            assert rate_limiter.acquire_alert_slot() is True
        assert rate_limiter.acquire_alert_slot() is False

        # Advance >1h: all three timestamps expire and the budget refills.
        clock["t"] = 1000.0 + 3601.0
        assert rate_limiter.alerts_remaining() == 3
        assert rate_limiter.acquire_alert_slot() is True

    def test_expired_rt_slots_freed(self, reset_windows, monkeypatch):
        clock = {"t": 500.0}
        monkeypatch.setattr(rate_limiter.time, "monotonic", lambda: clock["t"])

        for _ in range(2):
            assert rate_limiter.acquire_rt_slot() is True
        assert rate_limiter.acquire_rt_slot() is False

        clock["t"] = 500.0 + 3601.0
        assert rate_limiter.rt_remaining() == 2
        assert rate_limiter.acquire_rt_slot() is True
