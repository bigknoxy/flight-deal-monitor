"""Test scheduler job implementations."""

import asyncio
from unittest.mock import MagicMock, patch

from app.scheduler_jobs import run_cleanup


def test_scan_route_uses_searchapi():
    with patch("app.scanner.SearchAPIClient") as mock_client:
        with patch("app.scanner.is_flight_seen_recently", return_value=False):
            with patch("app.scanner.calculate_median_price", return_value=500.0):
                with patch("app.scanner.FLIClient") as mock_fli_cls:
                    from app.scanner import _scan_route

                    mock_fli = MagicMock()
                    mock_fli.search_flights.return_value = []
                    mock_fli_cls.return_value = mock_fli

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        session = MagicMock()
                        loop.run_until_complete(
                            _scan_route(session, "MCI", "LHR", "2024-06-01")
                        )
                        mock_client.assert_called_once()
                    finally:
                        loop.close()


def test_run_cleanup():
    mock_session = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    with patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session):
        with patch("app.scheduler_jobs.cleanup_expired_deals") as mock_cleanup:
            mock_cleanup.return_value = 5
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_cleanup())
                mock_cleanup.assert_called_once_with(mock_session)
            finally:
                loop.close()
