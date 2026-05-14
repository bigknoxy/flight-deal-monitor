"""Test deduplication utilities."""

from datetime import datetime, timedelta

import pytest

from app.models.flight import FlightDeal
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
    from unittest.mock import AsyncMock, patch

    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session:
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

        mock_session.commit = AsyncMock()

        await mark_flight_seen(mock_session, deal)

        assert deal.expired_at is not None
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_is_flight_seen_recently_true():
    """Test is_flight_seen_recently when flight was seen."""
    from unittest.mock import AsyncMock, patch

    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session:
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = FlightDeal(
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

        mock_session.execute.return_value = mock_result

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is True


@pytest.mark.asyncio
async def test_is_flight_seen_recently_false():
    """Test is_flight_seen_recently when flight not seen."""
    from unittest.mock import AsyncMock, patch

    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session:
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session.execute.return_value = mock_result

        is_seen = await is_flight_seen_recently(mock_session, "test_route")

        assert is_seen is False


@pytest.mark.asyncio
async def test_cleanup_expired_deals():
    """Test cleanup of expired deals."""
    from unittest.mock import AsyncMock, patch

    with patch("sqlalchemy.ext.asyncio.AsyncSession") as mock_session:
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

        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = [expired_deal]
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        count = await cleanup_expired_deals(mock_session)

        assert count == 1
        mock_session.delete.assert_called_once()
        mock_session.commit.assert_called_once()
