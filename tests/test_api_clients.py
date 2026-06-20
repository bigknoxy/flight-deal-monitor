"""Test API clients."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import AmadeusClient, DuffelClient


@pytest.fixture
def amadeus_client():
    """Create Amadeus client fixture."""
    return AmadeusClient()


@pytest.fixture
def duffel_client():
    """Create Duffel client fixture."""
    return DuffelClient()


@pytest.mark.asyncio
async def test_amadeus_get_token(amadeus_client):
    """Test Amadeus token retrieval."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 1800,
        }
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        token = await amadeus_client._get_token()

        assert token == "test_token"
        assert amadeus_client.token == "test_token"
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_amadeus_search_flights(amadeus_client):
    """Test Amadeus flight search."""

    async def mock_get_token():
        return "test_token"

    with patch.object(amadeus_client, "_get_token", side_effect=mock_get_token):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {
                        "price": {"total": "100.00"},
                        "validatingAirlineCodes": ["BA"],
                        "itineraries": [
                            {"segments": [{"flight": {"number": "BA123"}}]}
                        ],
                    }
                ]
            }
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            flights = await amadeus_client.search_flights("MCI", "LHR", "2024-06-01")

            assert len(flights) == 1
            assert flights[0]["price"]["total"] == "100.00"


@pytest.mark.asyncio
async def test_amadeus_get_flight_price(amadeus_client):
    """Test Amadeus price extraction."""
    flight_offer = {"price": {"total": "199.99"}}

    price = await amadeus_client.get_flight_price(flight_offer)

    assert price == 199.99


@pytest.mark.asyncio
async def test_amadeus_get_flight_price_invalid(amadeus_client):
    """Test Amadeus price extraction with invalid data."""
    flight_offer = {}

    price = await amadeus_client.get_flight_price(flight_offer)

    assert price == 0.0


@pytest.mark.asyncio
async def test_duffel_search_flights(duffel_client):
    """Test Duffel flight search."""
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"id": "req_123"}}

        mock_response2 = MagicMock()
        mock_response2.json.return_value = {
            "data": [
                {
                    "id": "off_123",
                    "total_amount": "150.00",
                }
            ]
        }

        mock_client.post.return_value = mock_response
        mock_client.get.return_value = mock_response2
        mock_client_class.return_value.__aenter__.return_value = mock_client

        offers = await duffel_client.search_flights("MCI", "LHR", "2024-06-01")

        assert len(offers) == 1


@pytest.mark.asyncio
async def test_duffel_get_flight_price(duffel_client):
    """Test Duffel price extraction."""
    offer = {"total_amount": "250.00"}

    price = await duffel_client.get_flight_price(offer)

    assert price == 250.00
