"""Interactive Telegram bot handler — long-poll for commands, fan-out alerts to subscribers."""

import asyncio
import logging

import httpx
from sqlalchemy import select

from app.config import config
from app.database import AsyncSessionLocal
from app.models.flight import FlightDeal
from app.models.telegram import TelegramSubscription

logger = logging.getLogger(__name__)

COMMANDS = {
    "/start": "Register your chat for deal alerts",
    "/deals": "Show latest 5 deals",
    "/routes": "Show monitored routes",
    "/subscribe": "Subscribe to a route: /subscribe ORIGIN DEST",
    "/unsubscribe": "Unsubscribe from all alerts",
    "/unsubscribe-route": "Unsubscribe from one route: /unsubscribe-route ORIGIN DEST",
    "/help": "Show this help",
}


def _escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    Escapes only the characters that Telegram treats as special.
    Callers should escape dynamic values BEFORE building Markdown formatting.
    """
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def _escape_md_value(text: str) -> str:
    """Escape a dynamic value for safe inclusion in MarkdownV2 messages.

    Use this for user-provided or dynamic values (prices, airports, URLs)
    that will NOT be formatted with bold/italic/link syntax.
    """
    return _escape_md(text)


class BotHandler:
    """Long-poll Telegram bot that handles commands and sends alerts."""

    def __init__(self) -> None:
        self.token = config.env.telegram_bot_token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._poll_task: asyncio.Task | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._offset = 0
        self._running = False

    async def start_polling(self) -> None:
        """Start long-polling for updates."""
        if not self.token:
            logger.info("No TELEGRAM_BOT_TOKEN set; skipping bot polling")
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.info("Telegram bot polling started")

    async def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        logger.info("Telegram bot polling stopped")

    async def _poll_loop(self) -> None:
        """Continuously poll getUpdates with a 30s long-poll timeout."""
        while self._running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self._offset, "timeout": 30}
                async with httpx.AsyncClient(timeout=35.0) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Bot poll error: {e}")
                await asyncio.sleep(5)

    async def _watchdog_loop(self) -> None:
        """Monitor _poll_task and restart it if it terminates unexpectedly.

        Does NOT restart during intentional shutdown (when _running is False).
        Uses exponential backoff capped at 60s to avoid hot loops.
        """
        backoff = 1.0
        while self._running:
            await asyncio.sleep(1.0)
            if self._poll_task is None:
                continue
            if self._poll_task.done():
                # Task is done but not cancelled — unexpected termination
                if not self._poll_task.cancelled():
                    logger.warning(
                        "Telegram bot poll loop terminated unexpectedly; restarting"
                    )
                    self._poll_task = asyncio.create_task(self._poll_loop())
                    backoff = min(backoff * 2, 60.0)
                    await asyncio.sleep(backoff)
                else:
                    # Task was cancelled during shutdown, exit watchdog
                    break
            else:
                # Poll task healthy, reset backoff
                backoff = 1.0

    async def _handle_update(self, update: dict) -> None:
        """Route an update to the appropriate command handler."""
        message = update.get("message")
        if not message:
            return
        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()
        if not text:
            return

        parts = text.split()
        command = parts[0].lower()

        if command == "/start":
            await self._cmd_start(chat_id)
        elif command == "/deals":
            await self._cmd_deals(chat_id)
        elif command == "/routes":
            await self._cmd_routes(chat_id)
        elif command == "/subscribe" and len(parts) >= 3:
            await self._cmd_subscribe(chat_id, parts[1].upper(), parts[2].upper())
        elif command == "/unsubscribe":
            await self._cmd_unsubscribe(chat_id)
        elif command == "/unsubscribe-route" and len(parts) >= 3:
            await self._cmd_unsubscribe_route(chat_id, parts[1].upper(), parts[2].upper())
        else:
            await self._cmd_help(chat_id)

    async def _send_message(self, chat_id: str, text: str) -> None:
        """Send a text message to a chat."""
        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(url, params=params)
        except Exception as e:
            logger.warning(f"Failed to send message to {chat_id}: {e}")

    async def _cmd_start(self, chat_id: str) -> None:
        """Register a chat for alerts."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TelegramSubscription).where(
                    TelegramSubscription.chat_id == chat_id,
                    TelegramSubscription.is_active.is_(True),
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                msg = "You are already registered for deal alerts!"
            else:
                sub = TelegramSubscription(chat_id=chat_id)
                session.add(sub)
                await session.commit()
                msg = (
                    "Welcome to Flight Deal Monitor!\n\n"
                    "You are now registered for deal alerts. "
                    "Use /help to see available commands."
                )
        await self._send_message(chat_id, msg)

    async def _cmd_deals(self, chat_id: str) -> None:
        """Show the latest 5 deals."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FlightDeal)
                .order_by(FlightDeal.seen_at.desc())
                .limit(5)
            )
            deals = result.scalars().all()
        if not deals:
            await self._send_message(chat_id, "No recent deals found.")
            return
        lines = ["*Latest Deals*"]
        for d in deals:
            emoji = "🚨" if d.deal_type == "mistake_fare" else "🔥"
            lines.append(
                f"{emoji} {_escape_md(d.origin)}→{_escape_md(d.destination)} "
                f"${d.current_price_usd:.0f} "
                f"({_escape_md(d.deal_type.replace('_', ' ').title())})"
            )
        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_routes(self, chat_id: str) -> None:
        """List monitored routes."""
        origins = config.app.home_airports
        destinations = config.app.destinations
        lines = ["*Monitored Routes*"]
        for o in origins:
            dests = ", ".join(_escape_md(d) for d in destinations)
            lines.append(f"From {_escape_md(o)}: {dests}")
        await self._send_message(chat_id, "\n".join(lines))

    async def _cmd_subscribe(self, chat_id: str, origin: str, destination: str) -> None:
        """Subscribe to a specific route."""
        async with AsyncSessionLocal() as session:
            sub = TelegramSubscription(
                chat_id=chat_id, origin=origin, destination=destination
            )
            session.add(sub)
            await session.commit()
        msg = (
            f"Subscribed to {_escape_md(origin)}→{_escape_md(destination)} alerts. "
            "You will receive deals for this route."
        )
        await self._send_message(chat_id, msg)

    async def _cmd_unsubscribe(self, chat_id: str) -> None:
        """Deactivate all subscriptions for a chat."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TelegramSubscription).where(
                    TelegramSubscription.chat_id == chat_id,
                    TelegramSubscription.is_active.is_(True),
                )
            )
            subs = result.scalars().all()
            for sub in subs:
                sub.is_active = False
            await session.commit()
        await self._send_message(chat_id, "You have been unsubscribed from all alerts.")

    async def _cmd_unsubscribe_route(
        self, chat_id: str, origin: str, destination: str
    ) -> None:
        """Deactivate subscription for a specific route only."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TelegramSubscription).where(
                    TelegramSubscription.chat_id == chat_id,
                    TelegramSubscription.is_active.is_(True),
                    TelegramSubscription.origin == origin,
                    TelegramSubscription.destination == destination,
                )
            )
            subs = result.scalars().all()
            if subs:
                for sub in subs:
                    sub.is_active = False
                await session.commit()
                msg = f"Unsubscribed from {origin}→{destination} alerts."
            else:
                msg = f"You are not subscribed to {origin}→{destination} alerts."
        await self._send_message(chat_id, msg)

    async def _cmd_help(self, chat_id: str) -> None:
        """Show available commands."""
        lines = ["*Available Commands*"]
        for cmd, desc in COMMANDS.items():
            lines.append(f"{_escape_md(cmd)} — {_escape_md(desc)}")
        await self._send_message(chat_id, "\n".join(lines))

    async def send_alert_to_subscribers(self, deal: FlightDeal) -> list[str]:
        """Send a deal alert to all active subscribers, returning message IDs."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(TelegramSubscription).where(
                    TelegramSubscription.is_active.is_(True),
                )
            )
            subs = result.scalars().all()
        if not subs:
            return []

        message = self._format_alert_message(deal)
        message_ids: list[str] = []
        for sub in subs:
            if sub.origin and sub.origin != deal.origin:
                continue
            if sub.destination and sub.destination != deal.destination:
                continue
            mid = await self._send_alert_to_chat(sub.chat_id, message)
            if mid:
                message_ids.append(mid)
        return message_ids

    async def _send_alert_to_chat(self, chat_id: str, message: str) -> str | None:
        """Send a pre-formatted alert to a single chat."""
        url = f"{self.base_url}/sendMessage"
        params = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params)
                response.raise_for_status()
                result = response.json()
            return str(result["result"]["message_id"])
        except Exception as e:
            logger.warning(f"Failed to send alert to {chat_id}: {e}")
            return None

    def _format_alert_message(self, flight_deal: FlightDeal) -> str:
        """Format flight deal alert message with MarkdownV2 escaping.

        Escapes only dynamic values (prices, airports, dates, URLs) BEFORE
        building Markdown formatting, so *bold* and [links](url) work correctly.
        """
        deal_emoji = "🚨" if flight_deal.deal_type == "mistake_fare" else "🔥"

        # Escape dynamic values that need escaping
        origin = _escape_md(flight_deal.origin)
        destination = _escape_md(flight_deal.destination)
        airline = _escape_md(flight_deal.airline)
        flight_numbers = _escape_md(flight_deal.flight_numbers)
        departure_date = _escape_md(flight_deal.departure_date)
        original_price = _escape_md(f"{flight_deal.original_price_usd:.2f}")
        current_price = _escape_md(f"{flight_deal.current_price_usd:.2f}")
        price_drop = _escape_md(f"{flight_deal.price_drop_percent:.1f}")
        booking_url = _escape_md(flight_deal.booking_url)

        message = f"""{deal_emoji} *Flight Deal Alert*

*{flight_deal.deal_type.replace('_', ' ').title()}*

📍 {origin} → {destination}
📅 {departure_date}
✈️ {airline}
🎫 {flight_numbers}

💰 ${original_price} → ${current_price}
📉 {price_drop}% OFF

[Book Now]({booking_url})

_Deal expires in 24 hours or when inventory runs out_"""

        return message


# Global bot handler instance
bot_handler = BotHandler()
