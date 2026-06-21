"""Test email notifier module — HTML rendering, SMTP, rate limiting."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import config
from app.notifiers.email import EmailNotifier, _render_html, _render_subject


class TestRenderHTML:
    """Test HTML email rendering."""

    def test_contains_route_and_prices(self, make_deal):
        deal = make_deal()
        html = _render_html(deal)
        assert "MCI" in html
        assert "LHR" in html
        assert "150.00" in html
        assert "500.00" in html
        assert "70.0" in html

    def test_deal_type_display_mistake_fare(self, make_deal):
        deal = make_deal(deal_type="mistake_fare")
        html = _render_html(deal)
        assert "Mistake Fare" in html
        assert "\U0001f6a8" in html

    def test_deal_type_display_flash_sale(self, make_deal):
        deal = make_deal(deal_type="flash_sale")
        html = _render_html(deal)
        assert "Flash Sale" in html
        assert "\U0001f525" in html

    def test_unknown_deal_type_shows_plane(self, make_deal):
        deal = make_deal(deal_type="unknown")
        html = _render_html(deal)
        assert "\u2708\ufe0f" in html

    def test_html_entities_escaped(self, make_deal):
        deal = make_deal(
            airline="AT&T Airlines", booking_url="https://example.com?a=1&b=2"
        )
        html = _render_html(deal)
        assert "AT&amp;T" in html
        assert "a=1&amp;b=2" in html

    def test_html_structure(self, make_deal):
        deal = make_deal()
        html = _render_html(deal)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "Book Now" in html
        assert "Deal expires" in html

    def test_booking_url_present(self, make_deal):
        deal = make_deal(booking_url="https://flights.example.com/book/123")
        html = _render_html(deal)
        assert "flights.example.com/book/123" in html

    def test_airline_and_flight_numbers(self, make_deal):
        deal = make_deal(airline="Delta", flight_numbers="DL123,DL456")
        html = _render_html(deal)
        assert "Delta" in html
        assert "DL123" in html
        assert "DL456" in html


class TestRenderSubject:
    """Test email subject line rendering."""

    def test_mistake_fare_subject(self, make_deal):
        deal = make_deal()
        subject = _render_subject(deal)
        assert "\U0001f6a8" in subject
        assert "MCI" in subject
        assert "LHR" in subject
        assert "150.00" in subject

    def test_flash_sale_subject(self, make_deal):
        deal = make_deal(deal_type="flash_sale", current_price_usd=250.0)
        subject = _render_subject(deal)
        assert "\U0001f525" in subject
        assert "250.00" in subject

    def test_subject_format(self, make_deal):
        deal = make_deal(
            origin="JFK",
            destination="LAX",
            current_price_usd=99.99,
            deal_type="flash_sale",
        )
        subject = _render_subject(deal)
        assert "JFK" in subject
        assert "LAX" in subject
        assert "99.99" in subject


class TestEmailNotifierSMTP:
    """Test EmailNotifier SMTP integration with mocked transport."""

    @pytest.fixture
    def notifier(self):
        n = EmailNotifier()
        n.host = "smtp.example.com"
        n.user = "user@example.com"
        n.password = "secret"
        return n

    @pytest.mark.asyncio
    async def test_send_alert_success(self, notifier, make_deal):
        deal = make_deal()
        with patch(
            "app.notifiers.email.aiosmtplib.send", new_callable=AsyncMock
        ) as mock_send:
            result = await notifier.send_alert(deal)
            assert result == "email_sent"
            assert notifier.alerts_sent_this_hour == 1
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_not_configured(self, make_deal):
        notifier = EmailNotifier()
        notifier.host = ""
        deal = make_deal()
        with patch(
            "app.notifiers.email.aiosmtplib.send", new_callable=AsyncMock
        ) as mock_send:
            result = await notifier.send_alert(deal)
            assert result is None
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_rate_limited(self, notifier, make_deal):
        deal = make_deal()
        notifier.alerts_sent_this_hour = 2
        notifier.last_hour_reset = 1
        with patch(
            "app.notifiers.email.aiosmtplib.send", new_callable=AsyncMock
        ) as mock_send:
            with patch.object(config.app, "max_alerts_per_hour", 2):
                with patch("time.time", return_value=3600.0):
                    result = await notifier.send_alert(deal)
            assert result is None
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_rate_limiter_resets_on_new_hour(self, notifier):
        with patch.object(config.app, "max_alerts_per_hour", 2):
            with patch("time.time", return_value=3600.0):
                notifier.alerts_sent_this_hour = 2
                notifier.last_hour_reset = 1
                assert notifier._is_rate_limited()

            with patch("time.time", return_value=7200.0):
                assert not notifier._is_rate_limited()
                assert notifier.alerts_sent_this_hour == 0

    @pytest.mark.asyncio
    async def test_send_alert_smtp_error(self, notifier, make_deal):
        deal = make_deal()
        with patch(
            "app.notifiers.email.aiosmtplib.send",
            side_effect=Exception("SMTP connection failed"),
        ):
            result = await notifier.send_alert(deal)
            assert result is None

    @pytest.mark.asyncio
    async def test_send_error_alert_success(self, notifier):
        with patch(
            "app.notifiers.email.aiosmtplib.send", new_callable=AsyncMock
        ) as mock_send:
            result = await notifier.send_error_alert("Test error message")
            assert result is True
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_error_alert_not_configured(self):
        notifier = EmailNotifier()
        notifier.host = ""
        with patch(
            "app.notifiers.email.aiosmtplib.send", new_callable=AsyncMock
        ) as mock_send:
            result = await notifier.send_error_alert("Test error")
            assert result is False
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_error_alert_failure(self, notifier):
        with patch(
            "app.notifiers.email.aiosmtplib.send",
            side_effect=Exception("SMTP error"),
        ):
            result = await notifier.send_error_alert("Test error message")
            assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_success(self, notifier):
        mock_smtp = AsyncMock()
        with patch("app.notifiers.email.aiosmtplib.SMTP", return_value=mock_smtp):
            result = await notifier.test_connection()
            assert result is True
            mock_smtp.connect.assert_called_once()
            mock_smtp.starttls.assert_called_once()
            mock_smtp.login.assert_called_once_with("user@example.com", "secret")
            mock_smtp.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_connection_not_configured(self):
        notifier = EmailNotifier()
        notifier.host = ""
        result = await notifier.test_connection()
        assert result is False

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, notifier):
        mock_smtp = AsyncMock()
        mock_smtp.connect.side_effect = Exception("Connection refused")
        with patch("app.notifiers.email.aiosmtplib.SMTP", return_value=mock_smtp):
            result = await notifier.test_connection()
            assert result is False


class TestSendDealAlertIntegration:
    """Test that _send_deal_alert calls all configured notifiers."""

    @pytest.mark.asyncio
    async def test_calls_all_notifiers(self, make_deal):
        from app.scheduler_jobs import _send_deal_alert

        deal = make_deal(id=1)
        session = AsyncMock()
        session.add = MagicMock()

        with patch("app.scheduler_jobs.telegram_bot") as mock_telegram:
            with patch("app.scheduler_jobs.email_notifier") as mock_email:
                with patch("app.scheduler_jobs.slack_notifier") as mock_slack:
                    with patch("app.scheduler_jobs.discord_notifier") as mock_discord:
                        mock_telegram.send_alert = AsyncMock(return_value="msg_123")
                        mock_email.send_alert = AsyncMock(return_value="email_sent")
                        mock_slack.send_alert = AsyncMock(return_value="sent")
                        mock_discord.send_alert = AsyncMock(return_value="sent")

                        result = await _send_deal_alert(session, deal)

                        mock_telegram.send_alert.assert_awaited_once_with(deal)
                        mock_email.send_alert.assert_awaited_once_with(deal)
                        mock_slack.send_alert.assert_awaited_once_with(deal)
                        mock_discord.send_alert.assert_awaited_once_with(deal)
                        assert result == (1, 1)
                        session.add.assert_called_once()
                        alert = session.add.call_args[0][0]
                        assert alert.status == "sent"
                        assert alert.telegram_message_id == "msg_123"

    @pytest.mark.asyncio
    async def test_telegram_failure_email_still_called(self, make_deal):
        from app.scheduler_jobs import _send_deal_alert

        deal = make_deal(id=2)
        session = AsyncMock()
        session.add = MagicMock()

        with patch("app.scheduler_jobs.telegram_bot") as mock_telegram:
            with patch("app.scheduler_jobs.email_notifier") as mock_email:
                with patch("app.scheduler_jobs.slack_notifier") as mock_slack:
                    with patch("app.scheduler_jobs.discord_notifier") as mock_discord:
                        mock_telegram.send_alert = AsyncMock(return_value=None)
                        mock_email.send_alert = AsyncMock(return_value="email_sent")
                        mock_slack.send_alert = AsyncMock(return_value="sent")
                        mock_discord.send_alert = AsyncMock(return_value="sent")

                        result = await _send_deal_alert(session, deal)

                        mock_telegram.send_alert.assert_awaited_once_with(deal)
                        mock_email.send_alert.assert_awaited_once_with(deal)
                        mock_slack.send_alert.assert_awaited_once_with(deal)
                        mock_discord.send_alert.assert_awaited_once_with(deal)
                        assert result == (1, 0)

    @pytest.mark.asyncio
    async def test_email_failure_does_not_block(self, make_deal):
        from app.scheduler_jobs import _send_deal_alert

        deal = make_deal(id=3)
        session = AsyncMock()
        session.add = MagicMock()

        with patch("app.scheduler_jobs.telegram_bot") as mock_telegram:
            with patch("app.scheduler_jobs.email_notifier") as mock_email:
                with patch("app.scheduler_jobs.slack_notifier") as mock_slack:
                    with patch("app.scheduler_jobs.discord_notifier") as mock_discord:
                        mock_telegram.send_alert = AsyncMock(return_value="msg_456")
                        mock_email.send_alert = AsyncMock(
                            side_effect=Exception("SMTP down")
                        )
                        mock_slack.send_alert = AsyncMock(return_value="sent")
                        mock_discord.send_alert = AsyncMock(return_value="sent")

                        result = await _send_deal_alert(session, deal)

                        mock_telegram.send_alert.assert_awaited_once_with(deal)
                        mock_email.send_alert.assert_awaited_once_with(deal)
                        mock_slack.send_alert.assert_awaited_once_with(deal)
                        mock_discord.send_alert.assert_awaited_once_with(deal)
                        assert result == (1, 1)

    @pytest.mark.asyncio
    async def test_all_notifiers_fail(self, make_deal):
        from app.scheduler_jobs import _send_deal_alert

        deal = make_deal(id=4)
        session = AsyncMock()
        session.add = MagicMock()

        with patch("app.scheduler_jobs.telegram_bot") as mock_telegram:
            with patch("app.scheduler_jobs.email_notifier") as mock_email:
                with patch("app.scheduler_jobs.slack_notifier") as mock_slack:
                    with patch("app.scheduler_jobs.discord_notifier") as mock_discord:
                        mock_telegram.send_alert = AsyncMock(return_value=None)
                        mock_email.send_alert = AsyncMock(return_value=None)
                        mock_slack.send_alert = AsyncMock(return_value=None)
                        mock_discord.send_alert = AsyncMock(return_value=None)

                        result = await _send_deal_alert(session, deal)

                        mock_telegram.send_alert.assert_awaited_once_with(deal)
                        mock_email.send_alert.assert_awaited_once_with(deal)
                        mock_slack.send_alert.assert_awaited_once_with(deal)
                        mock_discord.send_alert.assert_awaited_once_with(deal)
                        assert result == (1, 0)
