"""Tests for bot.py sync helpers (MarkdownV2 escaping + alert formatting).

These are deterministic sync functions; async bot glue is excluded (requires a
live Telegram token / network).
"""

from unittest.mock import MagicMock

from app.bot import BotHandler, _escape_md, _escape_md_value


def _fake_deal(**overrides) -> MagicMock:
    deal = MagicMock()
    deal.deal_type = "mistake_fare"
    deal.origin = "MCI"
    deal.destination = "LHR"
    deal.airline = "BA"
    deal.flight_numbers = "BA178"
    deal.departure_date = "2024-06-01"
    deal.original_price_usd = 900.0
    deal.current_price_usd = 300.0
    deal.price_drop_percent = 66.6
    deal.booking_url = "https://kayak.com/flights/MCI-LHR"
    for k, v in overrides.items():
        setattr(deal, k, v)
    return deal


class TestEscapeMarkdown:
    def test_escapes_special_chars(self):
        text = r"a*b[c]d(e)f~g`h#i+j=k|l{m}n.o!_>-"
        escaped = _escape_md(text)
        for ch in r"_*[]()~`>#+-=|{}.!":
            assert f"\\{ch}" in escaped

    def test_plain_text_unchanged(self):
        assert _escape_md("HELLO") == "HELLO"

    def test_escape_md_value_delegates(self):
        assert _escape_md_value("a.b") == _escape_md("a.b")


class TestFormatAlertMessage:
    def test_mistake_fare_uses_alarm_emoji(self):
        msg = BotHandler()._format_alert_message(_fake_deal())
        assert "🚨" in msg
        # Dynamic values are MarkdownV2-escaped (dots get a backslash).
        assert "MCI" in msg
        assert "LHR" in msg
        assert "66\\.6" in msg

    def test_flash_sale_uses_fire_emoji(self):
        msg = BotHandler()._format_alert_message(
            _fake_deal(deal_type="flash_sale")
        )
        assert "🔥" in msg
        assert "Flash Sale" in msg

    def test_prices_and_booking_url_present(self):
        msg = BotHandler()._format_alert_message(_fake_deal())
        assert "900\\.00" in msg
        assert "300\\.00" in msg
        assert "https://kayak\\.com/flights/MCI\\-LHR" in msg
