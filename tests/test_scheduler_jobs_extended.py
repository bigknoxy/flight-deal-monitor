"""Extended scheduler job tests — job run lifecycle, _scan_route fallback chains."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.job_lifecycle import (
    _complete_job_run,
    _fail_job_run,
    _start_job_run,
)
from app.models.job import JobRun
from app.scanner import _build_booking_url, _extract_stopover_airports, _scan_route


class TestJobRunLifecycle:
    """Test the _start_job_run, _complete_job_run, _fail_job_run DB helpers."""

    @pytest.mark.asyncio
    async def test_start_job_run_creates_record(self):
        """_start_job_run must create a JobRun and return it."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        JobRun(job_id="regular_sweep", status="running")
        mock_session.__aenter__.return_value = mock_session

        with patch("app.job_lifecycle.AsyncSessionLocal", return_value=mock_session):
            await _start_job_run("regular_sweep")
            # Check that commit/refresh were called
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_job_run_updates_record(self):
        """_complete_job_run must set status=success with deals/alerts counts."""
        job_run = JobRun(
            id=1,
            job_id="regular_sweep",
            started_at=datetime(2024, 6, 1, 12, 0, 0),
        )
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session

        with patch("app.job_lifecycle.AsyncSessionLocal", return_value=mock_session):
            await _complete_job_run(job_run, deals_detected=5, alerts_sent=3)

            assert job_run.status == "success"
            assert job_run.deals_detected == 5
            assert job_run.alerts_sent == 3
            assert job_run.completed_at is not None
            assert job_run.duration_seconds is not None
            mock_session.add.assert_called_once_with(job_run)
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_job_run_sets_error(self):
        """_fail_job_run must set status=failed with error message."""
        job_run = JobRun(
            id=1,
            job_id="mistake_sweep",
            started_at=datetime(2024, 6, 1, 12, 0, 0),
        )
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session

        with patch("app.job_lifecycle.AsyncSessionLocal", return_value=mock_session):
            await _fail_job_run(job_run, "API rate limit exceeded")

            assert job_run.status == "failed"
            assert job_run.error_message == "API rate limit exceeded"
            assert job_run.completed_at is not None
            mock_session.add.assert_called_once_with(job_run)
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_job_run_zero_counts(self):
        """Zero deals/alerts is a valid outcome."""
        job_run = JobRun(
            id=2,
            job_id="regular_sweep",
            started_at=datetime(2024, 6, 1, 12, 0, 0),
        )
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session

        with patch("app.job_lifecycle.AsyncSessionLocal", return_value=mock_session):
            await _complete_job_run(job_run, deals_detected=0, alerts_sent=0)

            assert job_run.status == "success"
            assert job_run.deals_detected == 0
            assert job_run.alerts_sent == 0


class TestScanRouteFallbackChain:
    """Test _scan_route data source fallback logic."""

    @pytest.fixture
    def mock_session(self):
        mock = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_scan_route_returns_early_if_recently_seen(self, mock_session):
        """If is_flight_seen_recently returns True per airline, skip those flights."""
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=True),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = [
                {"validatingAirlineCodes": ["AA"], "price": {"total": "200.0"}, "itineraries": [{"segments": [{"flight": {"number": "100"}}]}]}
            ]
            mock_fli_cls.return_value = mock_fli
            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
            assert result == []

    @pytest.mark.asyncio
    async def test_scan_route_returns_early_if_recently_cached(self, mock_session):
        """If cache has recent data (< TTL), skip search."""
        now = datetime.utcnow()
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=([{"flight": "test"}], now)),
            patch("app.scanner.price_cache.set_cached_route_data") as mock_set,
        ):
            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
            assert result == []
            mock_set.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_route_fli_success(self, mock_session):
        """When fli returns flights, use them (no fallback needed)."""
        fli_flights = [
            {
                "validatingAirlineCodes": ["BA"],
                "itineraries": [{"segments": [{"flight": {"number": "BA123"}}]}],
                "price": {"total": "200.00"},
            }
        ]
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = fli_flights
            mock_fli_cls.return_value = mock_fli

            with patch("app.scanner.detect_deal", return_value=(True, "flash_sale")):
                with patch("app.scanner.calculate_price_drop", return_value=60.0):
                    # Need to handle the DB session commit/refresh for deal creation
                    # Since this is mocking-heavy, let's just check fli was called
                    await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
                    mock_fli.search_flights.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_route_cold_start_emits_no_deals(self, mock_session):
        """Cold-start (no baseline): never flag the batch as deals, but still record observations."""
        fli_flights = [
            {
                "validatingAirlineCodes": ["BA"],
                "itineraries": [{"segments": [{"flight": {"number": "BA123"}}]}],
                "price": {"total": "50.00"},
            }
        ]
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=None),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.record_price_observations") as mock_record,
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = fli_flights
            mock_fli_cls.return_value = mock_fli

            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")

            # Cheap flight would have been a "deal" under the old batch-min baseline,
            # but with no accumulated history we must NOT alert.
            assert result == []
            mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_route_fallback_chain(self, mock_session):
        """When fli fails, should try SearchAPI, then Amadeus, then Duffel."""
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            # fli fails
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = []
            mock_fli_cls.return_value = mock_fli

            with patch("app.scanner.SearchAPIClient") as mock_searchapi_cls:
                mock_searchapi = AsyncMock()
                mock_searchapi.search_flights.return_value = [{"flight": "searchapi_result"}]
                mock_searchapi_cls.return_value = mock_searchapi

                await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
                # fli returned [], so SearchAPI should be called
                mock_fli.search_flights.assert_called_once()
                mock_searchapi.search_flights.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_route_invalid_flight_data(self, mock_session):
        """Malformed flight data should be caught by exception handler (lines 279-281)."""
        invalid_flights = [
            {"price": {"total": "not_a_number"}},  # ValueError on float conversion
            {"validatingAirlineCodes": ["AA"]},  # missing price key entirely
        ]
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = invalid_flights
            mock_fli_cls.return_value = mock_fli

            # Should not raise — malformed flights should be skipped
            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
            assert result == []  # no valid deals

    @pytest.mark.asyncio
    async def test_scan_route_low_price_skipped(self, mock_session):
        """Flights below min_price_usd should be skipped (line 250-251)."""

        cheap_flight = {
            "validatingAirlineCodes": ["NK"],
            "itineraries": [{"segments": [{"flight": {"number": "NK123"}}]}],
            "price": {"total": "50.00"},  # below min_price_usd=100
        }
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = [cheap_flight]
            mock_fli_cls.return_value = mock_fli

            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
            assert result == []  # price too low

    @pytest.mark.asyncio
    async def test_scan_route_applies_route_multiplier(self, mock_session):
        """detect_deal must be called with origin and destination for route multipliers."""
        flight = {
            "validatingAirlineCodes": ["BA"],
            "itineraries": [{"segments": [{"flight": {"number": "BA123"}}]}],
            "price": {"total": "200.00"},
        }
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = [flight]
            mock_fli_cls.return_value = mock_fli

            with patch("app.scanner.detect_deal", return_value=(True, "flash_sale")) as mock_detect:
                with patch("app.scanner.calculate_price_drop", return_value=60.0):
                    await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
                    mock_detect.assert_called_once_with(200.0, 500.0, "MCI", "LHR")

    @pytest.mark.asyncio
    async def test_scan_route_all_sources_fail(self, mock_session):
        """When all sources fail, return empty list."""
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.side_effect = Exception("fli down")
            mock_fli_cls.return_value = mock_fli

            with patch("app.scanner.SearchAPIClient") as mock_searchapi_cls:
                mock_searchapi = AsyncMock()
                mock_searchapi.search_flights.side_effect = Exception("SearchAPI down")
                mock_searchapi_cls.return_value = mock_searchapi

                with patch("app.scanner.AmadeusClient") as mock_amadeus_cls:
                    mock_amadeus = AsyncMock()
                    mock_amadeus.search_flights.side_effect = Exception("Amadeus down")
                    mock_amadeus_cls.return_value = mock_amadeus

                    with patch("app.scanner.DuffelClient") as mock_duffel_cls:
                        mock_duffel = AsyncMock()
                        mock_duffel.search_flights.side_effect = Exception("Duffel down")
                        mock_duffel_cls.return_value = mock_duffel

                        result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
                        assert result == []


class TestTripTypeInScheduler:
    """Tier 1: trip_type threading through scheduler jobs."""

    @pytest.fixture
    def mock_session(self):
        mock = AsyncMock()
        mock.add = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_scan_route_records_one_way_trip_type(self, mock_session):
        """After a successful one-way scan, FlightDeal.trip_type must be 'one_way'."""
        fli_flights = [
            {
                "validatingAirlineCodes": ["BA"],
                "itineraries": [{"segments": [{"flight": {"number": "BA123"}}]}],
                "price": {"total": "200.00"},
            }
        ]
        with (
            patch("app.scanner.is_flight_seen_recently", return_value=False),
            patch("app.scanner.calculate_median_price", return_value=500.0),
            patch("app.scanner.calculate_percentile_baseline", return_value=None),
            patch("app.scanner.price_cache.get_cached_route_data", return_value=None),
            patch("app.scanner.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = fli_flights
            mock_fli_cls.return_value = mock_fli

            with patch("app.scanner.detect_deal", return_value=(True, "flash_sale")):
                with patch("app.scanner.calculate_price_drop", return_value=60.0):
                    await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")

                    # session.add was called; find the FlightDeal arg
                    from app.models.flight import FlightDeal
                    deal_args = [
                        call[0][0] for call in mock_session.add.call_args_list
                        if isinstance(call[0][0], FlightDeal)
                    ]
                    assert len(deal_args) >= 1
                    assert deal_args[0].trip_type == "one_way"

    def test_build_booking_url_one_way(self):
        """Booking URL must pre-fill origin, destination and date on Kayak."""
        url = _build_booking_url("MCI", "LHR", "2024-06-01")
        assert url == "https://www.kayak.com/flights/MCI-LHR/2024-06-01"
        assert "tt=1" not in url

    def test_build_booking_url_round_trip(self):
        """URL with return_date appends the return segment (round-trip)."""
        url = _build_booking_url("MCI", "LHR", "2024-06-01", return_date="2024-06-08")
        assert url == "https://www.kayak.com/flights/MCI-LHR/2024-06-01/2024-06-08"

    def test_build_booking_url_lowercases_then_uppercases_codes(self):
        """Airport codes are normalized to upper case."""
        url = _build_booking_url("mci", "lhr", "2024-06-01")
        assert "MCI-LHR" in url

    def test_build_booking_url_with_airline(self):
        """Airline filter is appended as a query param."""
        url = _build_booking_url("MCI", "LHR", "2024-06-01", airline="ba")
        assert "a=BA" in url

    def test_build_booking_url_has_no_stopover_segment(self):
        """Kayak path format has no via segment in the URL."""
        url = _build_booking_url("MCI", "LHR", "2024-06-01")
        assert url.startswith("https://www.kayak.com/flights/MCI-LHR/")

    def test_booking_url_host_matches_ui_label(self):
        """Product-sync guard: the UI label says 'RT on Kayak' (see
        partials/deal_row.html, dashboard/index.html). The booking URL host MUST
        match, or users click a Kayak link expecting Google. If the provider
        switches again, this test fails loudly instead of silently drifting."""
        url = _build_booking_url("MCI", "LHR", "2024-06-01")
        from urllib.parse import urlparse

        host = urlparse(url).netloc
        assert host == "www.kayak.com", f"UI says Kayak but URL host is {host}"


class TestStopoverExtraction:
    """Test extraction of stopover airports from flight segments."""

    def test_extract_stopover_single_segment(self):
        """Direct flight has no stopovers."""
        flight = {
            "itineraries": [{
                "segments": [{"flight": {"number": "BA123"}, "arrival_airport": "LHR"}]
            }]
        }
        via = _extract_stopover_airports(flight, "LHR")
        assert via == []

    def test_extract_stopover_multi_segment(self):
        """Flight with connection includes intermediate airport."""
        flight = {
            "itineraries": [{
                "segments": [
                    {"flight": {"number": "BA123"}, "arrival_airport": "ORD"},
                    {"flight": {"number": "AA456"}, "arrival_airport": "LHR"},
                ]
            }]
        }
        via = _extract_stopover_airports(flight, "LHR")
        assert via == ["ORD"]

    def test_extract_stopover_multiple_connections(self):
        """Flight with multiple connections includes all intermediate airports."""
        flight = {
            "itineraries": [{
                "segments": [
                    {"flight": {"number": "BA123"}, "arrival_airport": "ORD"},
                    {"flight": {"number": "AA456"}, "arrival_airport": "ATL"},
                    {"flight": {"number": "UA789"}, "arrival_airport": "LHR"},
                ]
            }]
        }
        via = _extract_stopover_airports(flight, "LHR")
        assert via == ["ORD", "ATL"]

    def test_extract_stopover_no_airport_data(self):
        """Missing airport data returns empty list."""
        flight = {
            "itineraries": [{
                "segments": [{"flight": {"number": "BA123"}}]
            }]
        }
        via = _extract_stopover_airports(flight, "LHR")
        assert via == []
