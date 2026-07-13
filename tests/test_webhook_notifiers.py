"""Test Slack and Discord webhook notifiers — payload format, HTTP, rate limiting."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import config
from app.notifiers.discord import DiscordNotifier, discord_notifier
from app.notifiers.slack import SlackNotifier, slack_notifier


class TestSlackPayloadFormat:
    """SlackNotifier._build_blocks is pure logic — verify the blocks structure."""

    def test_header_block_has_emoji_and_route(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal()
        blocks = bot._build_blocks(deal)
        header = blocks[0]
        assert header["type"] == "header"
        assert "🚨" in header["text"]["text"]
        assert "MCI" in header["text"]["text"]
        assert "LHR" in header["text"]["text"]

    def test_mistake_fare_uses_emoji(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal(deal_type="mistake_fare")
        blocks = bot._build_blocks(deal)
        assert "🚨" in blocks[0]["text"]["text"]

    def test_flash_sale_uses_emoji(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal(deal_type="flash_sale")
        blocks = bot._build_blocks(deal)
        assert "🔥" in blocks[0]["text"]["text"]

    def test_deep_flash_uses_emoji(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal(deal_type="deep_flash")
        blocks = bot._build_blocks(deal)
        assert "⚡" in blocks[0]["text"]["text"]

    def test_route_fields_section(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal()
        blocks = bot._build_blocks(deal)
        route_section = blocks[1]
        assert route_section["type"] == "section"
        fields_text = "".join(f["text"] for f in route_section["fields"])
        assert "MCI → LHR" in fields_text
        assert "2024-06-01" in fields_text
        assert "BA" in fields_text
        assert "BA123" in fields_text

    def test_price_fields_section(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal()
        blocks = bot._build_blocks(deal)
        price_section = blocks[2]
        assert price_section["type"] == "section"
        fields_text = "".join(f["text"] for f in price_section["fields"])
        assert "$500.00" in fields_text
        assert "$150.00" in fields_text
        assert "70.0%" in fields_text
        assert "Mistake Fare" in fields_text

    def test_button_block(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal()
        blocks = bot._build_blocks(deal)
        actions = blocks[3]
        assert actions["type"] == "actions"
        button = actions["elements"][0]
        assert button["type"] == "button"
        assert button["url"] == "https://example.com/book"
        assert "Book Now" in button["text"]["text"]

    def test_flash_sale_deal_type_label(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal(deal_type="flash_sale")
        blocks = bot._build_blocks(deal)
        price_section = blocks[2]
        fields_text = "".join(f["text"] for f in price_section["fields"])
        assert "Flash Sale" in fields_text

    def test_deep_flash_deal_type_label(self, make_deal):
        bot = SlackNotifier()
        deal = make_deal(deal_type="deep_flash")
        blocks = bot._build_blocks(deal)
        price_section = blocks[2]
        fields_text = "".join(f["text"] for f in price_section["fields"])
        assert "Deep Flash" in fields_text


class TestDiscordEmbedFormat:
    """DiscordNotifier._build_embed is pure logic — verify embed structure."""

    def test_embed_title_contains_route_and_price(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal()
        embed = bot._build_embed(deal)
        assert "MCI → LHR" in embed["title"]
        assert "$150.00" in embed["title"]

    def test_embed_description_contains_details(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal()
        embed = bot._build_embed(deal)
        desc = embed["description"]
        assert "MCI → LHR" in desc
        assert "2024-06-01" in desc
        assert "BA" in desc
        assert "BA123" in desc

    def test_embed_fields(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal()
        embed = bot._build_embed(deal)
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Original Price"] == "$500.00"
        assert fields["Current Price"] == "$150.00"
        assert fields["Discount"] == "70.0%"
        assert fields["Deal Type"] == "Mistake Fare"

    def test_embed_mistake_fare_color_red(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal(deal_type="mistake_fare")
        embed = bot._build_embed(deal)
        assert embed["color"] == 15158332

    def test_embed_flash_sale_color_green(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal(deal_type="flash_sale")
        embed = bot._build_embed(deal)
        assert embed["color"] == 3066993

    def test_embed_deep_flash_color_orange(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal(deal_type="deep_flash")
        embed = bot._build_embed(deal)
        assert embed["color"] == 15105570

    def test_embed_url_and_footer(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal()
        embed = bot._build_embed(deal)
        assert embed["url"] == "https://example.com/book"
        assert embed["footer"]["text"] == "Flight Deal Monitor"

    def test_embed_flash_sale_fields(self, make_deal):
        bot = DiscordNotifier()
        deal = make_deal(deal_type="flash_sale")
        embed = bot._build_embed(deal)
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Deal Type"] == "Flash Sale"


class TestSlackNotifierRateLimiting:
    """Rate limiter must match TelegramBot behavior."""

    def test_rate_limiter_resets_on_new_hour(self):
        bot = SlackNotifier()
        with patch.object(config.app, "max_alerts_per_hour", 2):
            with patch("time.time", return_value=3600.0):
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 1
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 2
                assert bot._is_rate_limited()

            with patch("time.time", return_value=7200.0):
                assert not bot._is_rate_limited()
                assert bot.alerts_sent_this_hour == 0

    def test_rate_limiter_allows_below_max(self):
        bot = SlackNotifier()
        with patch.object(config.app, "max_alerts_per_hour", 5):
            with patch("time.time", return_value=3600.0):
                bot.alerts_sent_this_hour = 4
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 5
                assert bot._is_rate_limited()

    def test_rate_limiter_zero_threshold(self):
        bot = SlackNotifier()
        with patch.object(config.app, "max_alerts_per_hour", 0):
            with patch("time.time", return_value=3600.0):
                assert bot._is_rate_limited()


class TestDiscordNotifierRateLimiting:
    """Rate limiter must match TelegramBot behavior."""

    def test_rate_limiter_resets_on_new_hour(self):
        bot = DiscordNotifier()
        with patch.object(config.app, "max_alerts_per_hour", 2):
            with patch("time.time", return_value=3600.0):
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 1
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 2
                assert bot._is_rate_limited()

            with patch("time.time", return_value=7200.0):
                assert not bot._is_rate_limited()
                assert bot.alerts_sent_this_hour == 0

    def test_rate_limiter_allows_below_max(self):
        bot = DiscordNotifier()
        with patch.object(config.app, "max_alerts_per_hour", 5):
            with patch("time.time", return_value=3600.0):
                bot.alerts_sent_this_hour = 4
                assert not bot._is_rate_limited()
                bot.alerts_sent_this_hour = 5
                assert bot._is_rate_limited()

    def test_rate_limiter_zero_threshold(self):
        bot = DiscordNotifier()
        with patch.object(config.app, "max_alerts_per_hour", 0):
            with patch("time.time", return_value=3600.0):
                assert bot._is_rate_limited()


class TestSlackNotifierHTTP:
    """Mock HTTP calls to Slack webhook."""

    @pytest.fixture
    def bot(self):
        bot = SlackNotifier()
        bot.webhook_url = "https://hooks.slack.com/test"
        return bot

    @pytest.mark.asyncio
    async def test_send_alert_success(self, bot, make_deal):
        deal = make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_alert(deal)
            assert result == "sent"
            assert bot.alerts_sent_this_hour == 1

    @pytest.mark.asyncio
    async def test_send_alert_rate_limited(self, bot, make_deal):
        deal = make_deal()
        with patch.object(config.app, "max_alerts_per_hour", 2):
            bot.alerts_sent_this_hour = 2
            bot.last_hour_reset = 1
            with patch("time.time", return_value=3600.0):
                result = await bot.send_alert(deal)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_alert_http_error(self, bot, make_deal):
        deal = make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("HTTP 429 Too Many Requests")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_alert(deal)
            assert result is None

    @pytest.mark.asyncio
    async def test_test_connection_success(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_send_error_alert_success(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_error_alert("Test error message")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_error_alert_failure(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("API error")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_error_alert("Test error message")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_posts_correct_payload(self, bot, make_deal):
        """Verify the JSON payload sent to Slack has the correct blocks structure."""
        deal = make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await bot.send_alert(deal)

            call_kwargs = mock_client.post.call_args
            assert call_kwargs is not None
            _, kwargs = call_kwargs
            payload = kwargs["json"]
            assert "blocks" in payload
            assert payload["blocks"][0]["type"] == "header"
            assert payload["blocks"][3]["type"] == "actions"


class TestDiscordNotifierHTTP:
    """Mock HTTP calls to Discord webhook."""

    @pytest.fixture
    def bot(self):
        bot = DiscordNotifier()
        bot.webhook_url = "https://discord.com/api/webhooks/test"
        return bot

    @pytest.mark.asyncio
    async def test_send_alert_success(self, bot, make_deal):
        deal = make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_alert(deal)
            assert result == "sent"
            assert bot.alerts_sent_this_hour == 1

    @pytest.mark.asyncio
    async def test_send_alert_rate_limited(self, bot, make_deal):
        deal = make_deal()
        with patch.object(config.app, "max_alerts_per_hour", 2):
            bot.alerts_sent_this_hour = 2
            bot.last_hour_reset = 1
            with patch("time.time", return_value=3600.0):
                result = await bot.send_alert(deal)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_alert_http_error(self, bot, make_deal):
        deal = make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("HTTP 429")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_alert(deal)
            assert result is None

    @pytest.mark.asyncio
    async def test_test_connection_success(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection refused")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.test_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_send_error_alert_success(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_error_alert("Test error message")
            assert result is True

    @pytest.mark.asyncio
    async def test_send_error_alert_failure(self, bot):
        with patch("app.notifiers.base.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("API error")
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await bot.send_error_alert("Test error message")
            assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_posts_correct_payload(self, bot, make_deal):
        """Verify the JSON payload sent to Discord has the correct embed structure."""
        deal = make_deal()
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = MagicMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            await bot.send_alert(deal)

            call_kwargs = mock_client.post.call_args
            assert call_kwargs is not None
            _, kwargs = call_kwargs
            payload = kwargs["json"]
            assert "embeds" in payload
            assert len(payload["embeds"]) == 1
            embed = payload["embeds"][0]
            assert "title" in embed
            assert "fields" in embed


class TestSendDealAlertCallsAllNotifiers:
    """_send_deal_alert must call telegram, slack, and discord in parallel."""

    @pytest.mark.asyncio
    async def test_calls_all_three_notifiers(self, make_deal):
        deal = make_deal()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        with (
            patch("app.alert_dispatch.telegram_bot") as mock_telegram,
            patch("app.alert_dispatch.slack_notifier") as mock_slack,
            patch("app.alert_dispatch.discord_notifier") as mock_discord,
        ):
            mock_telegram.send_alert = AsyncMock(return_value="msg_123")
            mock_slack.send_alert = AsyncMock(return_value="sent")
            mock_discord.send_alert = AsyncMock(return_value="sent")

            from app.scheduler_jobs import _send_deal_alert

            deals, alerts = await _send_deal_alert(mock_session, deal)

            assert deals == 1
            assert alerts == 1
            mock_telegram.send_alert.assert_awaited_once_with(deal)
            mock_slack.send_alert.assert_awaited_once_with(deal)
            mock_discord.send_alert.assert_awaited_once_with(deal)

    @pytest.mark.asyncio
    async def test_alerts_sent_when_other_notifiers_succeed(self, make_deal):
        """Telegram failing no longer means the alert is lost — if slack or
        discord deliver, the deal is considered sent."""
        deal = make_deal()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        with (
            patch("app.alert_dispatch.telegram_bot") as mock_telegram,
            patch("app.alert_dispatch.slack_notifier") as mock_slack,
            patch("app.alert_dispatch.discord_notifier") as mock_discord,
        ):
            mock_telegram.send_alert = AsyncMock(return_value=None)
            mock_slack.send_alert = AsyncMock(return_value="sent")
            mock_discord.send_alert = AsyncMock(return_value="sent")

            from app.scheduler_jobs import _send_deal_alert

            deals, alerts = await _send_deal_alert(mock_session, deal)

            assert deals == 1
            assert alerts == 1
            mock_telegram.send_alert.assert_awaited_once_with(deal)
            mock_slack.send_alert.assert_awaited_once_with(deal)
            mock_discord.send_alert.assert_awaited_once_with(deal)

    @pytest.mark.asyncio
    async def test_handles_exception_from_notifier(self, make_deal):
        deal = make_deal()
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        with (
            patch("app.alert_dispatch.telegram_bot") as mock_telegram,
            patch("app.alert_dispatch.slack_notifier") as mock_slack,
            patch("app.alert_dispatch.discord_notifier") as mock_discord,
        ):
            mock_telegram.send_alert = AsyncMock(return_value="msg_123")
            mock_slack.send_alert = AsyncMock(side_effect=Exception("Slack down"))
            mock_discord.send_alert = AsyncMock(return_value="sent")

            from app.scheduler_jobs import _send_deal_alert

            deals, alerts = await _send_deal_alert(mock_session, deal)

            assert deals == 1
            assert alerts == 1  # Telegram still succeeded


class TestGlobalInstances:
    """Module-level global instances must exist."""

    def test_slack_notifier_global(self):
        assert slack_notifier is not None
        assert isinstance(slack_notifier, SlackNotifier)

    def test_discord_notifier_global(self):
        assert discord_notifier is not None
        assert isinstance(discord_notifier, DiscordNotifier)
