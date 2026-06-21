"""Email alert integration."""

import html
import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import config
from app.models.flight import FlightDeal
from app.notifiers.base import DEAL_EMOJIS, DEFAULT_DEAL_EMOJI, BaseNotifier

logger = logging.getLogger(__name__)


def _get_deal_emoji(deal_type: str) -> str:
    return DEAL_EMOJIS.get(deal_type, DEFAULT_DEAL_EMOJI)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
<div style="background-color: #f8f9fa; border-radius: 8px; padding: 20px;">
<div style="font-size: 48px; text-align: center;">{emoji}</div>
<h2 style="text-align: center; color: #333;">{deal_type}</h2>
<table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
<tr><td style="padding: 8px; color: #666;">Route</td><td style="padding: 8px; font-weight: bold;">{origin} → {destination}</td></tr>
<tr><td style="padding: 8px; color: #666;">Date</td><td style="padding: 8px; font-weight: bold;">{departure_date}</td></tr>
<tr><td style="padding: 8px; color: #666;">Airline</td><td style="padding: 8px; font-weight: bold;">{airline}</td></tr>
<tr><td style="padding: 8px; color: #666;">Flight</td><td style="padding: 8px; font-weight: bold;">{flight_numbers}</td></tr>
<tr><td style="padding: 8px; color: #666;">Original Price</td><td style="padding: 8px;">${original_price}</td></tr>
<tr><td style="padding: 8px; color: #666;">Deal Price</td><td style="padding: 8px; font-size: 18px; font-weight: bold; color: #e74c3c;">${current_price}</td></tr>
<tr><td style="padding: 8px; color: #666;">Savings</td><td style="padding: 8px; font-weight: bold; color: #27ae60;">{price_drop}% OFF</td></tr>
</table>
<a href="{booking_url}" style="display: block; text-align: center; background-color: #007bff; color: #fff; text-decoration: none; padding: 12px; border-radius: 4px; font-size: 16px;">Book Now</a>
<p style="text-align: center; color: #999; font-size: 12px; margin-top: 20px;">Deal expires in 24 hours or when inventory runs out</p>
</div>
</div>
</body>
</html>"""


def _render_html(deal: FlightDeal) -> str:
    emoji = _get_deal_emoji(deal.deal_type)
    deal_type = html.escape(deal.deal_type.replace("_", " ").title())
    origin = html.escape(deal.origin)
    destination = html.escape(deal.destination)
    departure_date = html.escape(deal.departure_date)
    airline = html.escape(deal.airline)
    flight_numbers = html.escape(deal.flight_numbers)
    original_price = f"{deal.original_price_usd:.2f}"
    current_price = f"{deal.current_price_usd:.2f}"
    price_drop = f"{deal.price_drop_percent:.1f}"
    booking_url = html.escape(deal.booking_url)

    return _HTML_TEMPLATE.format(
        emoji=emoji,
        deal_type=deal_type,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        airline=airline,
        flight_numbers=flight_numbers,
        original_price=original_price,
        current_price=current_price,
        price_drop=price_drop,
        booking_url=booking_url,
    )


def _render_subject(deal: FlightDeal) -> str:
    emoji = _get_deal_emoji(deal.deal_type)
    return (
        f"{emoji} Flight Deal: {deal.origin} \u2192 {deal.destination} - "
        f"${deal.current_price_usd:.2f}"
    )


def _build_message(
    subject: str, html_body: str | None = None, text_body: str | None = None
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.env.email_from
    msg["To"] = config.env.email_to
    if text_body:
        msg.set_content(text_body)
    if html_body:
        if text_body:
            msg.add_alternative(html_body, subtype="html")
        else:
            msg.set_content(html_body, subtype="html")
    return msg


class EmailNotifier(BaseNotifier):
    """Email notifier for sending flight deal alerts via SMTP."""

    def __init__(self) -> None:
        super().__init__()
        self.host = config.env.smtp_host
        self.port = config.env.smtp_port
        self.user = config.env.smtp_user
        self.password = config.env.smtp_pass

    async def send_alert(self, deal: FlightDeal) -> str | None:
        """Send a flight deal alert via email."""
        if self._is_rate_limited():
            logger.warning("Email rate limited: skipping alert")
            return None

        if not self.host:
            return None

        subject = _render_subject(deal)
        html_body = _render_html(deal)
        msg = _build_message(
            subject,
            html_body=html_body,
            text_body=f"Flight Deal: {deal.origin} → {deal.destination}",
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True,
            )
            self.alerts_sent_this_hour += 1
            logger.info(f"Sent email alert for {deal.route_id}")
            return "email_sent"
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return None

    async def send_error_alert(self, message: str) -> bool:
        """Send an error alert via email."""
        if not self.host:
            return False

        text = f"\u26a0\ufe0f Flight Deal Monitor Error\n\n{message}"
        msg = _build_message("\u26a0\ufe0f Flight Deal Monitor Error", text_body=text)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=True,
            )
            logger.info(f"Sent error email: {message[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to send error email: {e}")
            return False

    async def test_connection(self) -> bool:
        """Test SMTP connection."""
        if not self.host:
            return False

        try:
            smtp = aiosmtplib.SMTP(hostname=self.host, port=self.port, timeout=10.0)
            await smtp.connect()
            await smtp.starttls()
            if self.user:
                await smtp.login(self.user, self.password)
            await smtp.quit()
            logger.info(f"SMTP connection successful to {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"SMTP connection failed: {e}")
            return False


# Global notifier instance
email_notifier = EmailNotifier()
