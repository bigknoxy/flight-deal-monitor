import logging
import threading
import time

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, max_failures: int = 3, cooldown_seconds: int = 600):
        self._max_failures = max_failures
        self._cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._last_failure_time: dict[str, float] = {}
        self._open_until: dict[str, float] = {}

    def record_success(self, provider_name: str) -> None:
        with self._lock:
            self._failures[provider_name] = 0
            self._open_until.pop(provider_name, None)
            self._last_failure_time.pop(provider_name, None)

    def record_failure(self, provider_name: str) -> None:
        now = time.monotonic()
        with self._lock:
            count = self._failures.get(provider_name, 0) + 1
            self._failures[provider_name] = count
            self._last_failure_time[provider_name] = now
            if count >= self._max_failures:
                self._open_until[provider_name] = now + self._cooldown_seconds
                logger.warning(
                    f"Circuit BREAKER OPEN for {provider_name} "
                    f"({count} failures, cooldown {self._cooldown_seconds}s)"
                )

    def is_allowed(self, provider_name: str) -> bool:
        now = time.monotonic()
        with self._lock:
            open_until = self._open_until.get(provider_name)
            if open_until is not None:
                if now < open_until:
                    return False
                self._open_until.pop(provider_name, None)
                self._failures[provider_name] = 0
                self._last_failure_time.pop(provider_name, None)
                logger.info(f"Circuit RESET for {provider_name} (cooldown elapsed)")
            return True

    def state(self, provider_name: str) -> dict:
        with self._lock:
            return {
                "failures": self._failures.get(provider_name, 0),
                "open_until": self._open_until.get(provider_name),
            }

    def get_all_states(self) -> dict:
        """Get state for all tracked providers (for /health endpoint)."""
        import time as _time
        with self._lock:
            result = {}
            now = _time.monotonic()
            for provider in set(self._failures) | set(self._open_until):
                result[provider] = {
                    "failures": self._failures.get(provider, 0),
                    "open_until": self._open_until.get(provider),
                    "open": bool(
                        self._open_until.get(provider) and
                        self._open_until[provider] > now
                    ),
                }
            return result


circuit_breaker = CircuitBreaker()
