import asyncio
import os

import pytest

from app.scrapers.fli_client import FLIClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("FLI_INTEGRATION_TEST"),
    reason="Set FLI_INTEGRATION_TEST=1 to run",
)


@pytest.fixture
def client() -> FLIClient:
    return FLIClient()


class TestFLIClientIntegration:
    async def test_client_instantiation(self, client: FLIClient) -> None:
        assert client is not None
        assert hasattr(client, "searcher")
        assert hasattr(client, "search_flights")

    async def test_search_flights_returns_real_data(
        self, client: FLIClient,
    ) -> None:
        flights = await asyncio.to_thread(
            client.search_flights, "MCI", "AUS", "2026-08-15",
        )
        assert isinstance(flights, list)
        assert len(flights) > 0

    async def test_flight_data_structure(self, client: FLIClient) -> None:
        flights = await asyncio.to_thread(
            client.search_flights, "MCI", "AUS", "2026-08-15",
        )
        assert len(flights) > 0
        flight = flights[0]
        assert "validatingAirlineCodes" in flight
        assert isinstance(flight["validatingAirlineCodes"], list)
        assert len(flight["validatingAirlineCodes"]) > 0
        assert "itineraries" in flight
        assert isinstance(flight["itineraries"], list)
        assert len(flight["itineraries"]) > 0
        assert "segments" in flight["itineraries"][0]
        assert "price" in flight
        assert "total" in flight["price"]
        assert "booking_url" in flight

    async def test_booking_url_is_valid_google_flights_url(
        self, client: FLIClient,
    ) -> None:
        flights = await asyncio.to_thread(
            client.search_flights, "MCI", "AUS", "2026-08-15",
        )
        assert len(flights) > 0
        for flight in flights:
            url = flight.get("booking_url", "")
            assert url.startswith("https://www.google.com/travel/flights?q=")
            assert len(url) > len("https://www.google.com/travel/flights?q=")

    async def test_invalid_airport_codes_return_empty(
        self, client: FLIClient,
    ) -> None:
        flights = await asyncio.to_thread(
            client.search_flights, "ZZZZ", "XXXX", "2026-08-15",
        )
        assert isinstance(flights, list)
        assert len(flights) == 0

    async def test_handles_errors_gracefully(self, client: FLIClient) -> None:
        flights = await asyncio.to_thread(
            client.search_flights, "", "", "not-a-date",
        )
        assert isinstance(flights, list)
        assert len(flights) == 0
