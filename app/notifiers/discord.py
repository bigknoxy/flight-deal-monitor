"""Discord webhook notification channel."""

import logging

import httpx

from app.config import config
from app.models.flight import FlightDeal
from app.notifiers.base import WebhookNotifier

logger = logging.getLogger(__name__)


DEAL_COLORS: dict[str, int] = {
    "flash_sale": 3066993,
    "deep_flash": 15105570,
    "mistake_fare": 15158332,
}


class DiscordNotifier(WebhookNotifier):
    """Send flight deal alerts to Discord via webhook."""

    def __init__(self) -> None:
        super().__init__()
        self.webhook_url = config.env.discord_webhook_url

    def _get_color(self, deal_type: str) -> int:
        return DEAL_COLORS.get(deal_type, 3066993)

    def _build_embed(self, deal: FlightDeal) -> dict:
        embed = {
            "title": f"✈️ {deal.origin} → {deal.destination} — ${deal.current_price_usd:.2f}",
            "description": (
                f"**Route:** {deal.origin} → {deal.destination}\n"
                f"**Date:** {deal.departure_date}\n"
                f"**Airline:** {deal.airline}\n"
                f"**Flight:** {deal.flight_numbers}"
            ),
            "color": self._get_color(deal.deal_type),
            "url": deal.booking_url,
            "fields": [
                {
                    "name": "Original Price",
                    "value": f"${deal.original_price_usd:.2f}",
                    "inline": True,
                },
                {
                    "name": "Current Price",
                    "value": f"${deal.current_price_usd:.2f}",
                    "inline": True,
                },
                {
                    "name": "Discount",
                    "value": f"{deal.price_drop_percent:.1f}%",
                    "inline": True,
                },
                {
                    "name": "Deal Type",
                    "value": deal.deal_type.replace("_", " ").title(),
                },
            ],
            "footer": {"text": "Flight Deal Monitor"},
        }
        return embed

    async def send_alert(self, deal: FlightDeal) -> str | None:
        if self._is_rate_limited():
            logger.warning("Discord rate limited: skipping alert")
            return None

        embed = self._build_embed(deal)
        payload = {
            "embeds": [embed],
            "content": f"✈️ New Flight Deal: {deal.origin} → {deal.destination}",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
            self.alerts_sent_this_hour += 1
            logger.info(f"Sent Discord alert for {deal.route_id}")
            return "sent"
        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return None


discord_notifier = DiscordNotifier()
