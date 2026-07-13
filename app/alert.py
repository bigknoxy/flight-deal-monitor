"""Telegram alert integration."""

import logging
import time

import httpx

from app.config import config
from app.models.flight import FlightDeal

logger = logging.getLogger(__name__)

# Cap on error alerts per hour so a recurring failure can't spam Telegram.
_ERROR_ALERT_LIMIT = 5
_error_alert_timestamps: list[float] = []


def _error_alert_allowed() -> bool:
    """Sliding-window gate for error alerts (max _ERROR_ALERT_LIMIT/hour)."""
    now = time.monotonic()
    cutoff = now - 3600.0
    while _error_alert_timestamps and _error_alert_timestamps[0] < cutoff:
        _error_alert_timestamps.pop(0)
    if len(_error_alert_timestamps) >= _ERROR_ALERT_LIMIT:
        return False
    _error_alert_timestamps.append(now)
    return True


class TelegramBot:
    """Telegram bot for sending alerts."""

    def __init__(self) -> None:
        self.bot_token = config.env.telegram_bot_token
        self.chat_id = config.env.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.alerts_sent_this_hour = 0
        self.last_hour_reset = None

    async def send_alert(self, flight_deal: FlightDeal) -> str | None:
        """Send flight deal alert to Telegram.

        Fans out to all interactive bot subscribers first, then falls back
        to the legacy hardcoded chat_id for backward compat.
        """
        from app.bot import bot_handler

        # Interactive bot subscribers get the alert first.
        try:
            subscriber_ids = await bot_handler.send_alert_to_subscribers(flight_deal)
        except Exception:
            subscriber_ids = []
        if subscriber_ids:
            self.alerts_sent_this_hour += 1
            logger.info(
                f"Sent alert to {len(subscriber_ids)} subscriber(s) for {flight_deal.route_id}"
            )
            return subscriber_ids[0]

        # Legacy fallback: send to the hardcoded chat_id.
        if not self.chat_id:
            return None

        if self._is_rate_limited():
            logger.warning("Rate limited: skipping alert")
            return None

        message = self._format_alert_message(flight_deal)

        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params)
                response.raise_for_status()
                result = response.json()

            self.alerts_sent_this_hour += 1
            logger.info(f"Sent alert for {flight_deal.route_id}")
            return str(result["result"]["message_id"])

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return None

    def _format_alert_message(self, flight_deal: FlightDeal) -> str:
        """Format flight deal alert message."""
        deal_emoji = "🚨" if flight_deal.deal_type == "mistake_fare" else "🔥"

        message = f"""{deal_emoji} *Flight Deal Alert*

*{flight_deal.deal_type.replace('_', ' ').title()}*

📍 {flight_deal.origin} → {flight_deal.destination}
📅 {flight_deal.departure_date}
✈️ {flight_deal.airline}
🎫 {flight_deal.flight_numbers}

💰 ${flight_deal.original_price_usd:.2f} → ${flight_deal.current_price_usd:.2f}
📉 {flight_deal.price_drop_percent:.1f}% OFF

[Book Now]({flight_deal.booking_url})

_Deal expires in 24 hours or when inventory runs out_"""

        # Escape special characters for MarkdownV2
        escape_chars = r"_*[]()~`>#+-=|{}.!"
        for char in escape_chars:
            message = message.replace(char, f"\\{char}")

        return message

    def _is_rate_limited(self) -> bool:
        """Check if rate limit has been exceeded."""
        import time

        now = int(time.time() / 3600)  # Current hour

        if self.last_hour_reset != now:
            self.last_hour_reset = now
            self.alerts_sent_this_hour = 0

        return bool(self.alerts_sent_this_hour >= config.app.max_alerts_per_hour)

    async def send_error_alert(self, message: str) -> bool:
        """Send error alert to Telegram."""
        if not _error_alert_allowed():
            logger.warning("Error-alert budget exhausted for this hour; skipping")
            return False

        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": f"⚠️ *Flight Deal Monitor Error*\n\n{message}",
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params)
                response.raise_for_status()
            logger.info(f"Sent error alert: {message[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to send error alert: {e}")
            return False

    async def test_connection(self) -> bool:
        """Test Telegram bot connection."""
        url = f"{self.base_url}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                result = response.json()
                logger.info(f"Connected as @{result['result']['username']}")
                return True
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            return False


# Global bot instance
telegram_bot = TelegramBot()
