"""Test caching layer — TTLCache and PriceCache edge cases."""

import time
from unittest.mock import patch

import pytest

from app.cache import PriceCache, TTLCache


class TestTTLCache:
    """Pure data-structure tests for TTLCache."""

    def test_get_missing_key(self):
        cache = TTLCache(ttl_seconds=3600)
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = TTLCache(ttl_seconds=3600)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_overwrite_key(self):
        cache = TTLCache(ttl_seconds=3600)
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"

    def test_expiry_on_get(self):
        """Accessing an expired entry must return None and delete it."""
        cache = TTLCache(ttl_seconds=10)
        cache.set("key", "value")
        # Advance past TTL
        with patch("time.time", return_value=time.time() + 20):
            assert cache.get("key") is None
        # Internal dict should be cleaned
        assert "key" not in cache._cache

    def test_ttl_boundary(self):
        """Entry still valid just before TTL expires."""
        cache = TTLCache(ttl_seconds=10)
        base = time.time()
        with patch("time.time", return_value=base):
            cache.set("key", "value")
        # Exactly at TTL — check `time.time() - timestamp > self._ttl`
        # Since it's strictly greater (`>`), value should still be valid at exactly TTL
        with patch("time.time", return_value=base + 10):
            assert cache.get("key") == "value"
        # 1 second past TTL — should expire
        with patch("time.time", return_value=base + 11):
            assert cache.get("key") is None

    def test_clear(self):
        cache = TTLCache(ttl_seconds=3600)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert len(cache._cache) == 0

    def test_store_none_value(self):
        """None is a valid stored value (not same as missing key)."""
        cache = TTLCache(ttl_seconds=3600)
        cache.set("key", None)
        assert cache.get("key") is None
        # But key exists in cache
        assert "key" in cache._cache

    def test_multiple_keys_independent_expiry(self):
        cache = TTLCache(ttl_seconds=10)
        base = time.time()
        with patch("time.time", return_value=base):
            cache.set("early", "value1")
        with patch("time.time", return_value=base + 8):
            cache.set("late", "value2")

        # Both valid
        with patch("time.time", return_value=base + 9):
            assert cache.get("early") == "value1"
            assert cache.get("late") == "value2"

        # Early expired, late still valid
        with patch("time.time", return_value=base + 12):
            assert cache.get("early") is None
            assert cache.get("late") == "value2"


class TestPriceCache:
    """Tests for PriceCache which wraps TTLCache."""

    @pytest.mark.asyncio
    async def test_get_cached_route_data_miss(self):
        pc = PriceCache(default_ttl_seconds=3600)
        result = await pc.get_cached_route_data("MCI", "LHR", "2024-06-01")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_cached_route_data(self):
        pc = PriceCache(default_ttl_seconds=3600)
        flights = [{"price": {"total": "100.00"}}]
        await pc.set_cached_route_data("MCI", "LHR", "2024-06-01", flights)
        result = await pc.get_cached_route_data("MCI", "LHR", "2024-06-01")
        assert result is not None
        cached_flights, cached_time = result
        assert cached_flights == flights
        assert cached_time is not None

    @pytest.mark.asyncio
    async def test_clear_price_cache(self):
        pc = PriceCache(default_ttl_seconds=3600)
        await pc.set_cached_route_data("MCI", "LHR", "2024-06-01", [])
        pc.clear()
        result = await pc.get_cached_route_data("MCI", "LHR", "2024-06-01")
        assert result is None

    @pytest.mark.asyncio
    async def test_route_key_uniqueness(self):
        """Different routes must not collide in cache."""
        pc = PriceCache(default_ttl_seconds=3600)
        await pc.set_cached_route_data("MCI", "LHR", "2024-06-01", ["flight_a"])
        await pc.set_cached_route_data("JFK", "LAX", "2024-06-01", ["flight_b"])

        result_a = await pc.get_cached_route_data("MCI", "LHR", "2024-06-01")
        result_b = await pc.get_cached_route_data("JFK", "LAX", "2024-06-01")

        assert result_a[0] == ["flight_a"]
        assert result_b[0] == ["flight_b"]
