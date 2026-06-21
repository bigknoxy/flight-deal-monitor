"""Test scheduler job implementations."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def test_scan_route_uses_searchapi():
    with patch("app.scheduler_jobs.SearchAPIClient") as mock_client:
        with patch("app.scheduler_jobs.is_flight_seen_recently", return_value=False):
            with patch("app.scheduler_jobs.calculate_median_price", return_value=500.0):
                from app.scheduler_jobs import _scan_route

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
            from app.scheduler_jobs import run_cleanup
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_cleanup())
                mock_cleanup.assert_called_once_with(mock_session)
            finally:
                loop.close()
