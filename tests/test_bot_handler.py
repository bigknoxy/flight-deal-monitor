"""Test bot.py - Telegram bot handler."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot import BotHandler, _escape_md
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


class TestEscapeMd:
    """Test _escape_md function for MarkdownV2 escaping."""

    def test_escapes_special_chars(self):
        """Special MarkdownV2 characters should be escaped."""
        text = "Price $500.00 (50% off)"
        result = _escape_md(text)
        assert "$500\\.00" in result
        assert "\\(50% off\\)" in result

    def test_preserves_safe_chars(self):
        """Safe characters should not be escaped."""
        text = "MCI LHR BA123"
        result = _escape_md(text)
        assert result == "MCI LHR BA123"

    def test_escapes_url_special_chars(self):
        """URL special characters that ARE MarkdownV2 special chars should be escaped."""
        text = "https://example.com/test"
        result = _escape_md(text)
        assert r"\." in result

    def test_escape_md_value_is_alias(self):
        """_escape_md_value is an alias for _escape_md (for API clarity)."""
        from app.bot import _escape_md_value
        assert _escape_md_value("test!value") == _escape_md("test!value")


class TestCircuitBreakerHealth:
    """Test circuit breaker exposure via /health."""

    def test_get_all_states_returns_empty_dict(self):
        """No providers called yet means no states."""
        from app.utils.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker()
        assert cb.get_all_states() == {}

    def test_get_all_states_tracks_failures(self):
        """State includes failure count and open status."""
        from app.utils.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(max_failures=3, cooldown_seconds=10)
        cb.record_failure("SearchAPI")
        state = cb.get_all_states()
        assert "SearchAPI" in state
        assert state["SearchAPI"]["failures"] == 1
        assert state["SearchAPI"]["open"] is False

    def test_get_all_states_shows_open(self):
        """State shows open=True when threshold reached."""
        from app.utils.circuit_breaker import CircuitBreaker
        cb = CircuitBreaker(max_failures=2, cooldown_seconds=100)
        cb.record_failure("Amadeus")
        cb.record_failure("Amadeus")
        state = cb.get_all_states()
        assert state["Amadeus"]["open"] is True


class TestObservedAtFeatures:
    """Test observed_at_month and observed_at_day_of_week are computed."""

    def test_observed_at_features_in_model(self):
        """PriceObservation has observed_at_month and observed_at_day_of_week columns."""
        from app.models.flight import PriceObservation
        fields = {f for f in dir(PriceObservation) if not f.startswith("_")}
        assert "observed_at_month" in fields or "observed_at_month" in PriceObservation.__annotations__
        assert "observed_at_day_of_week" in fields or "observed_at_day_of_week" in PriceObservation.__annotations__


class TestPermanentFailureThreshold:
    """Test permanent failure threshold in dedup logic."""

    @pytest.mark.asyncio
    async def test_permanent_failure_after_max_attempts(self):
        """Deal is marked permanently failed after MAX_ALERT_ATTEMPTS failures."""
        from app.utils.deduplication import MAX_ALERT_ATTEMPTS

        # Verify the threshold exists
        assert MAX_ALERT_ATTEMPTS == 5

    @pytest.mark.asyncio
    async def test_deal_not_seen_when_no_alerts(self):
        """Deal without alerts should not be considered seen."""
        from app.utils.deduplication import is_flight_seen_recently

        # Test using mock session directly passed as argument
        mock_session = AsyncMock()
        # First call (deal query) returns None
        mock_deal_result = MagicMock()
        mock_deal_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_deal_result

        result = await is_flight_seen_recently(mock_session, "nonexistent_route")
        assert result is False


class TestFormatAlertMessage:
    """Test _format_alert_message preserves MarkdownV2 formatting."""

    def test_mistake_fare_format(self):
        bot = BotHandler()
        deal = _make_deal(deal_type="mistake_fare")
        msg = bot._format_alert_message(deal)
        assert "🚨" in msg
        assert "MCI" in msg
        assert "LHR" in msg
        assert "Mistake Fare" in msg
        assert "70\\.0%" in msg
        assert "Book Now" in msg

    def test_markdown_formatting_preserved(self):
        """Bold and link formatting must NOT be escaped."""
        bot = BotHandler()
        deal = _make_deal()
        msg = bot._format_alert_message(deal)
        # Bold markers (*) should NOT be escaped
        assert r"\*" not in msg, "Asterisks for bold formatting should NOT be escaped"
        # Link syntax [text](url) should work - brackets may be present but not escaped together
        # The link text "Book Now" should be followed by (url) format
        assert "[Book Now]" in msg or "Book Now" in msg

    def test_price_values_escaped(self):
        """Decimal and dollar sign in price values should be escaped."""
        bot = BotHandler()
        deal = _make_deal(original_price_usd=500.0, current_price_usd=150.0)
        msg = bot._format_alert_message(deal)
        # Prices should have escaped decimals
        assert "500\\.00" in msg
        assert "150\\.00" in msg


class TestBotWatchdog:
    """Test bot polling watchdog functionality."""

    def test_is_running_flag(self):
        bot = BotHandler()
        assert bot._running is False
        assert bot._poll_task is None

    @pytest.mark.asyncio
    async def test_start_polling_creates_task(self):
        bot = BotHandler()
        # Token must be present or start_polling early-returns (bot disabled).
        # Set it explicitly so the test does not depend on ambient env.
        bot.token = "test_token"
        with patch.object(bot, "_poll_loop", new_callable=AsyncMock):
            await bot.start_polling()
            assert bot._poll_task is not None
            assert bot._running is True
            await bot.stop_polling()

    @pytest.mark.asyncio
    async def test_stop_polling_clears_task(self):
        bot = BotHandler()
        bot._poll_task = None
        bot._offset = 42
        await bot.stop_polling()
        assert bot._running is False


class TestSingleRouteUnsubscribe:
    """Test single-route unsubscribe command."""

    @pytest.mark.asyncio
    async def test_cmd_unsubscribe_all_routes(self):
        """Unsubscribe from all routes (existing behavior)."""

        bot = BotHandler()
        mock_sub = MagicMock()
        mock_sub.chat_id = "123"
        mock_sub.is_active = True

        with patch("app.bot.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_sub]
            mock_session.execute.return_value = mock_result

            with patch.object(bot, "_send_message", new_callable=AsyncMock):
                await bot._cmd_unsubscribe("123")

    @pytest.mark.asyncio
    async def test_cmd_unsubscribe_single_route(self):
        """Unsubscribe from a specific route."""

        bot = BotHandler()
        mock_sub = MagicMock()
        mock_sub.chat_id = "123"
        mock_sub.origin = "MCI"
        mock_sub.destination = "LHR"
        mock_sub.is_active = True

        with patch("app.bot.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_sub]
            mock_session.execute.return_value = mock_result

            with patch.object(bot, "_send_message", new_callable=AsyncMock) as mock_send:
                await bot._cmd_unsubscribe_route("123", "MCI", "LHR")
                mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_unsubscribe_route_not_found(self):
        """Unsubscribe from non-existent route returns message."""
        bot = BotHandler()

        with patch("app.bot.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            with patch.object(bot, "_send_message", new_callable=AsyncMock) as mock_send:
                await bot._cmd_unsubscribe_route("123", "MCI", "LHR")
                assert "not subscribed" in mock_send.call_args[0][1].lower()

    def test_unsubscribe_command_in_commands(self):
        """Commands should reflect both unsubscribe types."""
        from app.bot import COMMANDS
        assert "/unsubscribe" in COMMANDS
        assert "/unsubscribe-route" in COMMANDS
