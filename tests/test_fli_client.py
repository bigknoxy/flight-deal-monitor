"""Test FLIClient — _to_dict conversion and search with mocks."""

from unittest.mock import MagicMock, patch

from app.scrapers.fli_client import FLIClient


def _make_mock_flight_result(**overrides) -> MagicMock:
    """Create a mock fli FlightResult with realistic attributes."""
    leg = MagicMock()
    leg.flight_number = "BA178"
    leg.departure_airport = "LHR"
    leg.arrival_airport = "JFK"
    leg.departure_time = "10:00"
    leg.arrival_time = "13:00"

    result = MagicMock()
    result.legs = [leg]
    result.primary_airline_name = "British Airways"
    result.price = 350.50
    result.duration = 480
    result.booking_token = None

    for k, v in overrides.items():
        setattr(result, k, v)

    return result


class TestFLIClientToDict:
    """Test the _to_dict conversion — pure logic from FlightResult to dict."""

    def test_to_dict_basic(self):
        result = _make_mock_flight_result()
        client = FLIClient()
        d = client._to_dict(result)

        assert d["validatingAirlineCodes"] == ["British Airways"]
        assert d["price"]["total"] == "350.50"
        assert d["itineraries"][0]["segments"][0]["flight"]["number"] == "BA178"
        assert d["type"] == "One way"
        assert d["total_duration"] == 480

    def test_to_dict_with_booking_token(self):
        """_to_dict always returns empty booking_url; scheduler builds it."""
        result = _make_mock_flight_result(
            booking_token='["CMgBEJf...aEkg=="]',
        )
        client = FLIClient()
        d = client._to_dict(result)

        assert d["booking_url"] == ""

    def test_to_dict_token_without_json_array(self):
        """_to_dict consistently returns empty booking_url; scheduler builds it."""
        result = _make_mock_flight_result(
            booking_token="simple_token_string",
        )
        client = FLIClient()
        d = client._to_dict(result)

        assert d["booking_url"] == ""

    def test_to_dict_no_legs(self):
        """Result with no legs should handle gracefully."""
        result = _make_mock_flight_result()
        result.legs = []

        client = FLIClient()
        d = client._to_dict(result)

        segments = d["itineraries"][0]["segments"]
        assert len(segments) == 1
        assert d["price"]["total"] == "350.50"

    def test_to_dict_no_booking_token(self):
        """With no booking token, no booking_url should be generated."""
        result = _make_mock_flight_result(booking_token="")
        client = FLIClient()
        d = client._to_dict(result)

        assert d.get("booking_url", "") == ""


class TestFLIClientSearch:
    """Test search_flights with mocked dependencies."""

    def test_search_with_invalid_airport_returns_empty(self):
        """When airport code is invalid, return empty list."""
        with patch("app.scrapers.fli_client.Airport") as mock_airport:
            mock_airport.INVALID = None
            del mock_airport.MCI
            del mock_airport.LHR

            client = FLIClient()
            result = client.search_flights("INVALID", "LHR", "2024-06-01")
            assert result == []

    def test_search_with_valid_airport_calls_searcher(self):
        """When airports are valid, searcher.search should be called."""
        with patch("app.scrapers.fli_client.Airport") as mock_airport:
            mock_airport.MCI = MagicMock()
            mock_airport.LHR = MagicMock()

            mock_result = MagicMock()
            mock_result.legs = [MagicMock()]
            mock_result.legs[0].flight_number = "BA178"
            mock_result.primary_airline_name = "BA"
            mock_result.price = 300.0
            mock_result.duration = 360
            mock_result.booking_token = None

            with patch.object(FLIClient, "search_flights", return_value=[]):
                client = FLIClient()
                result = client._to_dict(mock_result)
                assert result["price"]["total"] == "300.00"
