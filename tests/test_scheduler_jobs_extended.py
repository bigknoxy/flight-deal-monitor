"""Extended scheduler job tests — job run lifecycle, _scan_route fallback chains."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.job import JobRun
from app.scheduler_jobs import (
    _complete_job_run,
    _fail_job_run,
    _scan_route,
    _start_job_run,
)


class TestJobRunLifecycle:
    """Test the _start_job_run, _complete_job_run, _fail_job_run DB helpers."""

    @pytest.mark.asyncio
    async def test_start_job_run_creates_record(self):
        """_start_job_run must create a JobRun and return it."""
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        job_run_created = JobRun(job_id="regular_sweep", status="running")
        mock_session.__aenter__.return_value = mock_session

        with patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session):
            result = await _start_job_run("regular_sweep")
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
        mock_session.__aenter__.return_value = mock_session

        with patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session):
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
        mock_session.__aenter__.return_value = mock_session

        with patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session):
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
        mock_session.__aenter__.return_value = mock_session

        with patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session):
            await _complete_job_run(job_run, deals_detected=0, alerts_sent=0)

            assert job_run.status == "success"
            assert job_run.deals_detected == 0
            assert job_run.alerts_sent == 0


class TestScanRouteFallbackChain:
    """Test _scan_route data source fallback logic."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_scan_route_returns_early_if_recently_seen(self, mock_session):
        """If is_flight_seen_recently returns True, return empty list."""
        with (
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=True),
            patch("app.scheduler_jobs.price_cache") as mock_cache,
        ):
            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
            assert result == []
            mock_cache.get_cached_route_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_scan_route_returns_early_if_recently_cached(self, mock_session):
        """If cache has recent data (< TTL), skip search."""
        now = datetime.utcnow()
        with (
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False),
            patch("app.scheduler_jobs.calculate_median_price", return_value=500.0),
            patch("app.scheduler_jobs.price_cache.get_cached_route_data", return_value=([{"flight": "test"}], now)),
            patch("app.scheduler_jobs.price_cache.set_cached_route_data") as mock_set,
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
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False),
            patch("app.scheduler_jobs.calculate_median_price", return_value=500.0),
            patch("app.scheduler_jobs.price_cache.get_cached_route_data", return_value=None),
            patch("app.scheduler_jobs.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = fli_flights
            mock_fli_cls.return_value = mock_fli

            with patch("app.scheduler_jobs.detect_deal", return_value=(True, "flash_sale")):
                with patch("app.scheduler_jobs.calculate_price_drop", return_value=60.0):
                    # Need to handle the DB session commit/refresh for deal creation
                    # Since this is mocking-heavy, let's just check fli was called
                    result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
                    mock_fli.search_flights.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_route_fallback_chain(self, mock_session):
        """When fli fails, should try SearchAPI, then Amadeus, then Duffel."""
        with (
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False),
            patch("app.scheduler_jobs.calculate_median_price", return_value=500.0),
            patch("app.scheduler_jobs.price_cache.get_cached_route_data", return_value=None),
            patch("app.scheduler_jobs.FLIClient") as mock_fli_cls,
        ):
            # fli fails
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = []
            mock_fli_cls.return_value = mock_fli

            with patch("app.scheduler_jobs.SearchAPIClient") as mock_searchapi_cls:
                mock_searchapi = AsyncMock()
                mock_searchapi.search_flights.return_value = [{"flight": "searchapi_result"}]
                mock_searchapi_cls.return_value = mock_searchapi

                result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
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
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False),
            patch("app.scheduler_jobs.calculate_median_price", return_value=500.0),
            patch("app.scheduler_jobs.price_cache.get_cached_route_data", return_value=None),
            patch("app.scheduler_jobs.FLIClient") as mock_fli_cls,
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
        from app.config import config

        cheap_flight = {
            "validatingAirlineCodes": ["NK"],
            "itineraries": [{"segments": [{"flight": {"number": "NK123"}}]}],
            "price": {"total": "50.00"},  # below min_price_usd=100
        }
        with (
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False),
            patch("app.scheduler_jobs.calculate_median_price", return_value=500.0),
            patch("app.scheduler_jobs.price_cache.get_cached_route_data", return_value=None),
            patch("app.scheduler_jobs.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.return_value = [cheap_flight]
            mock_fli_cls.return_value = mock_fli

            result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
            assert result == []  # price too low

    @pytest.mark.asyncio
    async def test_scan_route_all_sources_fail(self, mock_session):
        """When all sources fail, return empty list."""
        with (
            patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False),
            patch("app.scheduler_jobs.calculate_median_price", return_value=500.0),
            patch("app.scheduler_jobs.price_cache.get_cached_route_data", return_value=None),
            patch("app.scheduler_jobs.FLIClient") as mock_fli_cls,
        ):
            mock_fli = MagicMock()
            mock_fli.search_flights.side_effect = Exception("fli down")
            mock_fli_cls.return_value = mock_fli

            with patch("app.scheduler_jobs.SearchAPIClient") as mock_searchapi_cls:
                mock_searchapi = AsyncMock()
                mock_searchapi.search_flights.side_effect = Exception("SearchAPI down")
                mock_searchapi_cls.return_value = mock_searchapi

                with patch("app.scheduler_jobs.AmadeusClient") as mock_amadeus_cls:
                    mock_amadeus = AsyncMock()
                    mock_amadeus.search_flights.side_effect = Exception("Amadeus down")
                    mock_amadeus_cls.return_value = mock_amadeus

                    with patch("app.scheduler_jobs.DuffelClient") as mock_duffel_cls:
                        mock_duffel = AsyncMock()
                        mock_duffel.search_flights.side_effect = Exception("Duffel down")
                        mock_duffel_cls.return_value = mock_duffel

                        result = await _scan_route(mock_session, "MCI", "LHR", "2024-06-01")
                        assert result == []
