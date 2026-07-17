import time
from datetime import datetime
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        value, timestamp = self._cache[key]
        if time.time() - timestamp > self._ttl:
            del self._cache[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        self._cache.clear()


class PriceCache:
    def __init__(self, default_ttl_seconds: int = 6 * 60 * 60):
        self._cache = TTLCache(default_ttl_seconds)

    async def get_cached_route_data(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None = None,
        suffix: str = "",
    ) -> tuple[list[dict], datetime] | None:
        key = self._build_key(origin, destination, departure_date, return_date, suffix)
        data = self._cache.get(key)
        if data is None:
            return None
        flights, timestamp = data
        return (flights, datetime.fromtimestamp(timestamp))

    async def set_cached_route_data(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        flights: list[dict],
        return_date: str | None = None,
        suffix: str = "",
    ) -> None:
        key = self._build_key(origin, destination, departure_date, return_date, suffix)
        self._cache.set(key, (flights, time.time()))

    @staticmethod
    def _build_key(
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str | None,
        suffix: str,
    ) -> str:
        date_part = departure_date if not return_date else f"{departure_date}-{return_date}"
        return f"{origin}:{destination}:{date_part}:{suffix}"

    def clear(self) -> None:
        self._cache.clear()


price_cache = PriceCache()
