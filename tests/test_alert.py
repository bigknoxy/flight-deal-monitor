"""Test Telegram alert module — formatting, rate limiting, HTTP integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.alert import TelegramBot
from app.config import config
from app.models.flight import FlightDeal


def _make_deal(**kwargs) -> FlightDeal:
    """Create a FlightDeal with defaults for testing."""
    defaults = dict(
        route_id="test_route",
        origin="MCI",
        destination="LHR",
        departure_date="2024-06-01",
        airline="BA",
        flight_numbers="BA123",
        original_price_usd=500.0,
        current_price_usd=150.0,
        price_drop_percent=70.0,
        deal_type="mistake_fare",
        booking_url="https://example.com/book",
    )
    defaults.update(kwargs)
    return FlightDeal(**defaults)


class TestFormatAlertMessage:
    """_format_alert_message is pure logic — test edge cases."""

    def test_mistake_fare_format(self):
        bot = TelegramBot()
        deal = _make_deal(deal_type="mistake_fare")
        msg = bot._format_alert_message(deal)
        assert "🚨" in msg
        assert "MCI" in msg
        assert "LHR" in msg
        assert "Mistake Fare" in msg
        # Bold formatting should be preserved, not escaped
        assert r"\*" not in msg, "Asterisks should NOT be escaped"
        assert "[Book Now](" in msg  # Link format preserved

    def test_flash_sale_format(self):
        bot = TelegramBot()
        deal = _make_deal(deal_type="flash_sale", current_price_usd=250.0, price_drop_percent=50.0)
        msg = bot._format_alert_message(deal)
        assert "🔥" in msg
        assert "Flash Sale" in msg
        assert r"\*" not in msg  # No escaped asterisks

    def test_markdown_special_chars_escaped_in_values(self):
        """Characters special to Telegram MarkdownV2 in dynamic values are escaped, but formatting is preserved."""
        bot = TelegramBot()
        deal = _make_deal(
            booking_url="https://example.com/test?a=b&c=d",
            price_drop_percent=50.0,
            current_price_usd=250.0,
        )
        msg = bot._format_alert_message(deal)
        # URLs have dots which must be escaped
        assert "example\\.com" in msg
        # Hyphens in dates must be escaped
        assert "2024\\-06\\-01" in msg
        # Bold formatting preserved
        assert r"\*" not in msg

    def test_rate_limiter_resets_on_new_hour(self):
        """_is_rate_limited must reset counter each hour."""
        bot = TelegramBot()
        # The rate limiter uses config.app.max_alerts_per_hour
        with patch.object(config.app, "max_alerts_per_hour", 2):
            with patch("time.time", return_value=3600.0):  # hour 1
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 1
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 2
                assert bot._is_rate_limited()

            # Advance to next hour — should reset
            with patch("time.time", return_value=7200.0):  # hour 2
                assert not bot._is_rate_limited()
                assert bot.alerts_sent_this_hour == 0

    def test_rate_limiter_allows_below_max(self):
        bot = TelegramBot()
        with patch.object(config.app, "max_alerts_per_hour", 5):
            with patch("time.time", return_value=3600.0):
                bot.alerts_sent_this_hour = 4
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 5
                assert bot._is_rate_limited()

    def test_rate_limiter_zero_threshold(self):
        """If max_alerts_per_hour is 0, every alert is rate-limited (0 >= 0)."""
        bot = TelegramBot()
        with patch.object(config.app, "max_alerts_per_hour", 0):
            with patch("time.time", return_value=3600.0):
                # With max=0: alerts_sent_this_hour (0) >= 0 → True
                assert bot._is_rate_limited()


class TestTelegramBotHTTP:
    """Tests that mock HTTP calls to Telegram API."""

    @pytest.fixture
    def bot(self):
        return TelegramBot()

    @pytest.mark.asyncio
    async def test_send_alert_success(self, bot):
        deal = _make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"result": {"message_id": "12345"}}
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_alert(deal)
            assert result == "12345"
            assert bot.alerts_sent_this_hour == 1

    @pytest.mark.asyncio
    async def test_send_alert_rate_limited(self, bot):
        """When rate-limited, should return None without calling API."""
        deal = _make_deal()
        with patch.object(config.app, "max_alerts_per_hour", 2):
            # Must set last_hour_reset so _is_rate_limited doesn't reset counter
            bot.alerts_sent_this_hour = 2
            bot.last_hour_reset = 1  # match int(time.time()/3600)
            with patch("time.time", return_value=3600.0):
                result = await bot.send_alert(deal)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_alert_http_error(self, bot):
        deal = _make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("HTTP 429 Too Many Requests")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_alert(deal)
            assert result is None

    @pytest.mark.asyncio
    async def test_test_connection_success(self, bot):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"result": {"username": "test_bot"}}
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, bot):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_send_error_alert_success(self, bot):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            result = await bot.send_error_alert("Test error message")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_error_alert_failure(self, bot):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("API error")
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            result = await bot.send_error_alert("Test error message")
            assert result is False
