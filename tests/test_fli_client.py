"""Test FLIClient — _to_dict conversion and search with mocks."""

import json
from enum import Enum
from unittest.mock import MagicMock, patch

from app.scrapers.fli_client import FLIClient, FLISearchError, _json_default, _to_dict


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
        d = _to_dict(result)

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
        d = _to_dict(result)

        assert d["booking_url"] == ""

    def test_to_dict_token_without_json_array(self):
        """_to_dict consistently returns empty booking_url; scheduler builds it."""
        result = _make_mock_flight_result(
            booking_token="simple_token_string",
        )
        d = _to_dict(result)

        assert d["booking_url"] == ""

    def test_to_dict_no_legs(self):
        """Result with no legs should handle gracefully."""
        result = _make_mock_flight_result()
        result.legs = []

        d = _to_dict(result)

        segments = d["itineraries"][0]["segments"]
        assert len(segments) == 1
        assert d["price"]["total"] == "350.50"

    def test_to_dict_no_booking_token(self):
        """With no booking token, no booking_url should be generated."""
        result = _make_mock_flight_result(booking_token="")
        d = _to_dict(result)

        assert d.get("booking_url", "") == ""

    def test_to_dict_with_enum_arrival_airport(self):
        """fli returns arrival_airport as an Airport enum; _to_dict must
        store it losslessly (the enum itself is serializable via _json_default
        in the subprocess, not here). Regression for the empty-UI crash where
        json.dumps choked on the non-serializable Airport enum."""

        class Airport(Enum):
            JFK = "JFK"

        result = _make_mock_flight_result()
        result.legs[0].arrival_airport = Airport.JFK
        d = _to_dict(result)

        assert d["itineraries"][0]["segments"][0]["arrival_airport"] is Airport.JFK

    def test_to_dict_with_none_price(self):
        """A result with price=None must not raise NoneType.__format__;
        it falls back to 0.00 so one bad result can't sink a whole route."""
        result = _make_mock_flight_result(price=None)
        d = _to_dict(result)

        assert d["price"]["total"] == "0.00"

    def test_to_dict_with_zero_price(self):
        """An explicit 0.0 price is preserved (not treated as missing)."""
        result = _make_mock_flight_result(price=0.0)
        d = _to_dict(result)

        assert d["price"]["total"] == "0.00"


class TestFLIClientJsonDefault:
    """Test the json.dumps fallback used by the fli subprocess.

    Regression coverage for the empty-UI bug: fli emits Airport enum members
    that plain json.dumps cannot serialize, crashing the search subprocess.
    """

    def test_json_default_coerces_enum_to_value(self):
        class Airport(Enum):
            JFK = "JFK"

        assert _json_default(Airport.JFK) == "JFK"

    def test_json_default_serializes_enum_result(self):
        class Airport(Enum):
            LHR = "LHR"

        payload = {"flights": [{"arrival": Airport.LHR}]}
        # Must not raise TypeError
        serialized = json.dumps(payload, default=_json_default)
        assert '"LHR"' in serialized


class TestFLIClientSearch:
    """Test search_flights — subprocess-based, mocks subprocess.run."""

    def test_search_returns_flights_from_subprocess(self):
        """Valid subprocess output is parsed and returned."""
        flights = [
            {
                "validatingAirlineCodes": ["BA"],
                "price": {"total": "300.00"},
            }
        ]
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"flights": flights})
        mock_proc.stderr = ""

        with patch("app.scrapers.fli_client.subprocess.run", return_value=mock_proc):
            client = FLIClient()
            result = client.search_flights("MCI", "LHR", "2024-06-01")
            assert result == flights

    def test_search_with_invalid_airport_returns_empty(self):
        """When the subprocess reports a genuine empty result, return []."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({"flights": []})
        mock_proc.stderr = ""

        with patch("app.scrapers.fli_client.subprocess.run", return_value=mock_proc):
            client = FLIClient()
            result = client.search_flights("INVALID", "LHR", "2024-06-01")
            assert result == []

    def test_search_subprocess_failure_raises_flisearcherror(self):
        """Non-zero subprocess exit raises FLISearchError."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "fli crashed"

        with patch("app.scrapers.fli_client.subprocess.run", return_value=mock_proc):
            client = FLIClient()
            try:
                client.search_flights("MCI", "LHR", "2024-06-01")
                assert False, "expected FLISearchError"
            except FLISearchError:
                pass

    def test_search_invalid_json_raises_flisearcherror(self):
        """Garbage subprocess stdout raises FLISearchError."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "not json"
        mock_proc.stderr = ""

        with patch("app.scrapers.fli_client.subprocess.run", return_value=mock_proc):
            client = FLIClient()
            try:
                client.search_flights("MCI", "LHR", "2024-06-01")
                assert False, "expected FLISearchError"
            except FLISearchError:
                pass

    def test_search_timeout_raises_flisearcherror(self):
        """subprocess timeout is converted to FLISearchError."""
        import subprocess as sp

        with patch(
            "app.scrapers.fli_client.subprocess.run",
            side_effect=sp.TimeoutExpired(cmd=[], timeout=40),
        ):
            client = FLIClient()
            try:
                client.search_flights("MCI", "LHR", "2024-06-01", timeout=30)
                assert False, "expected FLISearchError"
            except FLISearchError:
                pass
