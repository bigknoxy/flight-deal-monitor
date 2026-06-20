"""Test SearchAPI client — normalization, price extraction, edge cases."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.searchapi import SearchAPIClient


class TestNormalizeFlight:
    """_normalize_flight is pure logic — test all edge cases."""

    def setup_method(self):
        self.client = SearchAPIClient()

    def test_normalize_basic(self):
        raw = {
            "flights": [{"airline": "BA", "flight_number": " BA123 "}],
            "price": 25000,  # cents
            "type": "One way",
            "total_duration": 320,
        }
        result = self.client._normalize_flight(raw)
        assert result["validatingAirlineCodes"] == ["BA"]
        assert result["price"]["total"] == "250.00"
        assert result["itineraries"][0]["segments"][0]["flight"]["number"] == "BA123"
        assert result["total_duration"] == 320

    def test_normalize_zero_price(self):
        raw = {"flights": [], "price": 0}
        result = self.client._normalize_flight(raw)
        assert result["price"]["total"] == "0.00"
        assert result["validatingAirlineCodes"] == ["Unknown"]

    def test_normalize_none_price(self):
        raw = {"flights": [], "price": None}
        result = self.client._normalize_flight(raw)
        assert result["price"]["total"] == "0.00"

    def test_normalize_string_price(self):
        """Handle malformed price that is string."""
        raw = {"flights": [], "price": "invalid"}
        result = self.client._normalize_flight(raw)
        assert result["price"]["total"] == "0.00"

    def test_normalize_empty_segments(self):
        """flights list empty — should handle gracefully."""
        raw = {
            "flights": [],
            "price": 10000,
        }
        result = self.client._normalize_flight(raw)
        assert result["validatingAirlineCodes"] == ["Unknown"]
        assert result["price"]["total"] == "100.00"
        assert result["itineraries"][0]["segments"] == []

    def test_normalize_missing_flights_key(self):
        """flights key entirely missing from raw data."""
        raw = {"price": 20000}
        result = self.client._normalize_flight(raw)
        assert result["validatingAirlineCodes"] == ["Unknown"]
        assert result["price"]["total"] == "200.00"

    def test_normalize_multiple_segments(self):
        raw = {
            "flights": [
                {"airline": "BA", "flight_number": "BA178"},
                {"airline": "AA", "flight_number": " AA456 "},
            ],
            "price": 35000,
        }
        result = self.client._normalize_flight(raw)
        assert len(result["itineraries"][0]["segments"]) == 2
        assert result["itineraries"][0]["segments"][0]["flight"]["number"] == "BA178"
        assert result["itineraries"][0]["segments"][1]["flight"]["number"] == "AA456"

    def test_normalize_flight_number_whitespace_removed(self):
        raw = {
            "flights": [{"airline": "NK", "flight_number": " NK 123 "}],
            "price": 5000,
        }
        result = self.client._normalize_flight(raw)
        assert result["itineraries"][0]["segments"][0]["flight"]["number"] == "NK123"

    def test_normalize_cents_conversion_precision(self):
        """Price in cents should convert to dollars with 2 decimal places."""
        raw = {"flights": [], "price": 19999}
        result = self.client._normalize_flight(raw)
        assert result["price"]["total"] == "199.99"

    def test_normalize_large_price(self):
        raw = {"flights": [], "price": 999999}
        result = self.client._normalize_flight(raw)
        assert result["price"]["total"] == "9999.99"


class TestSearchAPIGetFlightPrice:
    def setup_method(self):
        self.client = SearchAPIClient()

    @pytest.mark.asyncio
    async def test_get_flight_price_success(self):
        price = await self.client.get_flight_price({"price": {"total": "199.99"}})
        assert price == 199.99

    @pytest.mark.asyncio
    async def test_get_flight_price_invalid_key(self):
        price = await self.client.get_flight_price({})
        assert price == 0.0

    @pytest.mark.asyncio
    async def test_get_flight_price_none_value(self):
        price = await self.client.get_flight_price({"price": None})
        assert price == 0.0

    @pytest.mark.asyncio
    async def test_get_flight_price_string_value(self):
        """If 'total' is a string, should still parse it."""
        price = await self.client.get_flight_price({"price": {"total": "300.50"}})
        assert price == 300.50


class TestSearchAPISearchFlights:
    """Integration-level tests with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_search_flights_combines_best_and_other(self):
        client = SearchAPIClient()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "best_flights": [
                    {"flights": [{"airline": "BA", "flight_number": "BA100"}], "price": 20000}
                ],
                "other_flights": [
                    {"flights": [{"airline": "AA", "flight_number": "AA200"}], "price": 15000}
                ],
            }
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            results = await client.search_flights("MCI", "LHR", "2024-06-01")
            assert len(results) == 2
            assert results[0]["validatingAirlineCodes"] == ["BA"]
            assert results[1]["validatingAirlineCodes"] == ["AA"]

    @pytest.mark.asyncio
    async def test_search_flights_max_results_respected(self):
        client = SearchAPIClient()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "best_flights": [
                    {"flights": [{"airline": "BA", "flight_number": f"BA{i}"}], "price": 20000}
                    for i in range(5)
                ],
                "other_flights": [
                    {"flights": [{"airline": "AA", "flight_number": f"AA{i}"}], "price": 15000}
                    for i in range(5)
                ],
            }
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            results = await client.search_flights("MCI", "LHR", "2024-06-01", max_results=3)
            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_search_flights_no_results(self):
        client = SearchAPIClient()
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"best_flights": [], "other_flights": []}
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            results = await client.search_flights("MCI", "XXX", "2024-06-01")
            assert results == []
