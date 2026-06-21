"""Slack webhook notification channel."""

import logging

import httpx

from app.config import config
from app.models.flight import FlightDeal
from app.notifiers.base import DEAL_EMOJIS, DEFAULT_DEAL_EMOJI, WebhookNotifier

logger = logging.getLogger(__name__)


class SlackNotifier(WebhookNotifier):
    """Send flight deal alerts to Slack via incoming webhook."""

    def __init__(self) -> None:
        super().__init__()
        self.webhook_url = config.env.slack_webhook_url

    def _get_deal_emoji(self, deal_type: str) -> str:
        return DEAL_EMOJIS.get(deal_type, DEFAULT_DEAL_EMOJI)

    def _build_blocks(self, deal: FlightDeal) -> list[dict]:
        emoji = self._get_deal_emoji(deal.deal_type)
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Flight Deal Alert: {deal.origin} → {deal.destination}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Route:*\n{deal.origin} → {deal.destination}",
                    },
                    {"type": "mrkdwn", "text": f"*Dates:*\n{deal.departure_date}"},
                    {"type": "mrkdwn", "text": f"*Airline:*\n{deal.airline}"},
                    {"type": "mrkdwn", "text": f"*Flight:*\n{deal.flight_numbers}"},
                ],
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Original Price:*\n${deal.original_price_usd:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Current Price:*\n${deal.current_price_usd:.2f}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Discount:*\n{deal.price_drop_percent:.1f}% OFF",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Deal Type:*\n{deal.deal_type.replace('_', ' ').title()}",
                    },
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✈️ Book Now",
                            "emoji": True,
                        },
                        "url": deal.booking_url,
                    },
                ],
            },
        ]
        return blocks

    async def send_alert(self, deal: FlightDeal) -> str | None:
        if self._is_rate_limited():
            logger.warning("Slack rate limited: skipping alert")
            return None

        blocks = self._build_blocks(deal)
        payload = {
            "blocks": blocks,
            "text": f"Flight Deal: {deal.origin} → {deal.destination}",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
            self.alerts_sent_this_hour += 1
            logger.info(f"Sent Slack alert for {deal.route_id}")
            return "sent"
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return None


slack_notifier = SlackNotifier()
