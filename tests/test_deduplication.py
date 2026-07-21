"""Test deduplication utilities."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.flight import AlertHistory, FlightDeal
from app.utils import (
    cleanup_expired_deals,
    generate_deal_hash,
    is_flight_seen_recently,
    mark_flight_seen,
)


def test_generate_deal_hash():
    """Test deal hash generation."""
    hash_1 = generate_deal_hash("MCI", "LHR", "2024-06-01", "BA", 300.0)
    hash_2 = generate_deal_hash("MCI", "LHR", "2024-06-01", "BA", 300.0)
    hash_3 = generate_deal_hash("MCI", "LHR", "2024-06-01", "BA", 350.0)

    assert hash_1 == hash_2
    assert hash_1 != hash_3
    assert len(hash_1) == 64  # SHA256 hex length


@pytest.mark.asyncio
async def test_mark_flight_seen():
    """Test marking flight as seen."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_cls.return_value = mock_session

        deal = FlightDeal(
            route_id="test_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
        )

        await mark_flight_seen(mock_session, deal)

        assert deal.expired_at is not None
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_is_flight_seen_recently_true():
    """Test is_flight_seen_recently when flight was seen and alert delivered."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        deal = FlightDeal(
            route_id="test_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
            seen_at=datetime.utcnow(),
            expired_at=datetime.utcnow() + timedelta(hours=12),
        )

        mock_deal_result = MagicMock()
        mock_deal_result.scalar_one_or_none.return_value = deal

        # Mock scalars().all() for the alert query (new API)
        mock_alert_result = MagicMock()
        mock_alert_result.scalars.return_value.all.return_value = [
            AlertHistory(flight_deal_id=1, status="sent")
        ]

        mock_session.execute.side_effect = [mock_deal_result, mock_alert_result]

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is True


@pytest.mark.asyncio
async def test_is_flight_seen_recently_false():
    """Test is_flight_seen_recently when flight not seen."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session.execute.return_value = mock_result

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is False


@pytest.mark.asyncio
async def test_is_flight_seen_recently_retries_on_failed_alert():
    """If the most recent alert for a seen deal was 'failed', allow retry."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        deal = FlightDeal(
            id=1,
            route_id="test_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
            seen_at=datetime.utcnow(),
            expired_at=datetime.utcnow() + timedelta(hours=12),
        )

        mock_deal_result = MagicMock()
        mock_deal_result.scalar_one_or_none.return_value = deal

        mock_alert_result = MagicMock()
        mock_alert_result.scalars.return_value.all.return_value = [
            AlertHistory(flight_deal_id=1, status="failed")
        ]

        mock_session.execute.side_effect = [mock_deal_result, mock_alert_result]

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is False


@pytest.mark.asyncio
async def test_is_flight_seen_recently_retries_on_rate_limited_alert():
    """If the most recent alert was 'rate_limited', allow retry."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        deal = FlightDeal(
            id=1,
            route_id="test_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
            seen_at=datetime.utcnow(),
            expired_at=datetime.utcnow() + timedelta(hours=12),
        )

        mock_deal_result = MagicMock()
        mock_deal_result.scalar_one_or_none.return_value = deal

        mock_alert_result = MagicMock()
        mock_alert_result.scalars.return_value.all.return_value = [
            AlertHistory(flight_deal_id=1, status="rate_limited")
        ]

        mock_session.execute.side_effect = [mock_deal_result, mock_alert_result]

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is False


@pytest.mark.asyncio
async def test_is_flight_seen_recently_no_alert_history_retries():
    """If a seen deal has no AlertHistory rows at all, allow retry."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        deal = FlightDeal(
            id=1,
            route_id="test_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
            seen_at=datetime.utcnow(),
            expired_at=datetime.utcnow() + timedelta(hours=12),
        )

        mock_deal_result = MagicMock()
        mock_deal_result.scalar_one_or_none.return_value = deal

        mock_alert_result = MagicMock()
        mock_alert_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_deal_result, mock_alert_result]

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is False


@pytest.mark.asyncio
async def test_cleanup_expired_deals():
    """Test cleanup of expired deals."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        expired_deal = FlightDeal(
            route_id="expired_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
            expired_at=datetime.utcnow() - timedelta(hours=1),
        )

        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = [expired_deal]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars_result

        mock_session.execute.return_value = mock_result

        count = await cleanup_expired_deals(mock_session)

        assert count == 1
        mock_session.delete.assert_called_once()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_expired_deals_rollback_on_error():
    """Test cleanup rolls back on exception during delete loop."""
    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session_cls.return_value = mock_session

        expired_deal = FlightDeal(
            route_id="expired_route",
            origin="MCI",
            destination="LHR",
            departure_date="2024-06-01",
            airline="BA",
            flight_numbers="BA123",
            original_price_usd=500.0,
            current_price_usd=300.0,
            price_drop_percent=40.0,
            deal_type="flash_sale",
            booking_url="https://example.com",
            expired_at=datetime.utcnow() - timedelta(hours=1),
        )

        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = [expired_deal]

        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars_result

        mock_session.execute.return_value = mock_result
        # Make delete succeed but commit fail
        mock_session.commit.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError, match="DB error"):
            await cleanup_expired_deals(mock_session)

        # Verify rollback was called on error
        mock_session.rollback.assert_called_once()
