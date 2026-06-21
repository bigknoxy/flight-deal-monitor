"""Base notifier interface."""

import time
from abc import ABC, abstractmethod

import httpx

from app.config import config
from app.models.flight import FlightDeal

DEAL_EMOJIS: dict[str, str] = {
    "mistake_fare": "🚨",
    "flash_sale": "🔥",
    "deep_flash": "⚡",
}
DEFAULT_DEAL_EMOJI = "✈️"


class BaseNotifier(ABC):
    """Abstract base class for alert notifiers."""

    def __init__(self) -> None:
        self.alerts_sent_this_hour = 0
        self.last_hour_reset: int | None = None

    def _is_rate_limited(self) -> bool:
        now = int(time.time() / 3600)
        if self.last_hour_reset != now:
            self.last_hour_reset = now
            self.alerts_sent_this_hour = 0
        return bool(self.alerts_sent_this_hour >= config.app.max_alerts_per_hour)

    @abstractmethod
    async def send_alert(self, deal: FlightDeal) -> str | None:
        """Send a flight deal alert. Returns a message ID or None on failure."""

    @abstractmethod
    async def send_error_alert(self, message: str) -> bool:
        """Send an error alert. Returns True if sent successfully."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test the notifier connection. Returns True if connected."""


class WebhookNotifier(BaseNotifier):
    webhook_url: str = ""

    async def _post(self, payload: dict, timeout: float = 30.0) -> bool:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.post(self.webhook_url, json=payload)
                res.raise_for_status()
            return True
        except Exception:
            return False

    async def send_error_alert(self, message: str) -> bool:
        if not self.webhook_url:
            return False
        return await self._post({"text": message})

    async def test_connection(self) -> bool:
        if not self.webhook_url:
            return False
        return await self._post({"text": "Test from Flight Deal Monitor"}, timeout=10.0)
