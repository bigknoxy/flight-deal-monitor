"""Test scheduler job implementations."""

import asyncio
from unittest.mock import MagicMock, patch


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
