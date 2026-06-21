"""Test long weekend date pair generation and sweep lifecycle."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.utils.long_weekend import get_long_weekend_date_pairs


class TestGetLongWeekendDatePairs:

    def test_returns_thursday_and_friday_starts(self):
        """Should return pairs starting on Thursdays and Fridays."""
        pairs = get_long_weekend_date_pairs(look_ahead_months=1)
        assert len(pairs) > 0
        for depart, ret in pairs:
            d = datetime.strptime(depart, "%Y-%m-%d")
            r = datetime.strptime(ret, "%Y-%m-%d")
            assert d.weekday() in {3, 4}
            assert (r - d).days == 3

    def test_return_date_is_three_days_later(self):
        """Thu→Sun and Fri→Mon should be exactly 3 days."""
        pairs = get_long_weekend_date_pairs(look_ahead_months=1)
        for depart, ret in pairs:
            d = datetime.strptime(depart, "%Y-%m-%d")
            r = datetime.strptime(ret, "%Y-%m-%d")
            assert (r - d).days == 3

    def test_no_duplicate_pairs(self):
        """Same date pair should not appear twice."""
        pairs = get_long_weekend_date_pairs(look_ahead_months=12)
        keys = {f"{d}:{r}" for d, r in pairs}
        assert len(keys) == len(pairs)

    def test_look_ahead_months_controls_range(self):
        """More months should produce more pairs."""
        pairs_1 = get_long_weekend_date_pairs(look_ahead_months=1)
        pairs_12 = get_long_weekend_date_pairs(look_ahead_months=12)
        assert len(pairs_12) >= len(pairs_1)

    def test_all_departures_are_thursday_or_friday(self):
        """Every departure date must be Thursday (3) or Friday (4)."""
        pairs = get_long_weekend_date_pairs(look_ahead_months=3)
        for depart, _ in pairs:
            d = datetime.strptime(depart, "%Y-%m-%d")
            assert d.weekday() in {3, 4}, f"{depart} is not Thu/Fri"

    def test_all_returns_are_sunday_or_monday(self):
        """Thu→Sun returns Sunday (6), Fri→Mon returns Monday (0)."""
        pairs = get_long_weekend_date_pairs(look_ahead_months=3)
        for depart, ret in pairs:
            d = datetime.strptime(depart, "%Y-%m-%d")
            r = datetime.strptime(ret, "%Y-%m-%d")
            if d.weekday() == 3:
                assert r.weekday() == 6, f"{depart}→{ret} should be Thu→Sun"
            elif d.weekday() == 4:
                assert r.weekday() == 0, f"{depart}→{ret} should be Fri→Mon"

    def test_returns_iso_format_strings(self):
        """Date strings should be YYYY-MM-DD format."""
        pairs = get_long_weekend_date_pairs(look_ahead_months=1)
        for depart, ret in pairs:
            assert len(depart) == 10
            assert len(ret) == 10
            assert depart[4] == "-"
            assert ret[4] == "-"


class TestLongWeekendSweepLifecycle:

    @pytest.mark.asyncio
    async def test_long_weekend_sweep_success(self):
        """Run long weekend sweep through its success path."""
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
        ):
            from app.scheduler_jobs import run_long_weekend_sweep

            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_long_weekend_sweep()

            mock_start.assert_called_once_with("long_weekend_sweep")
            mock_complete.assert_called_once_with(mock_job_run, 0, 0)

    @pytest.mark.asyncio
    async def test_long_weekend_sweep_failure(self):
        """When long weekend sweep fails, _fail_job_run should be called."""
        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", side_effect=Exception("timeout")),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._fail_job_run") as mock_fail,
        ):
            from app.scheduler_jobs import run_long_weekend_sweep

            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_long_weekend_sweep()

            mock_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_weekend_sweep_with_deals(self):
        """With deals found, alerts should be sent and recorded."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        deal = MagicMock()
        deal.id = 1
        deal.deal_type = "flash_sale"

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[deal]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
            patch("app.scheduler_jobs.telegram_bot.send_alert", return_value="msg_1") as mock_send,
        ):
            from app.scheduler_jobs import run_long_weekend_sweep

            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_long_weekend_sweep()

            mock_send.assert_called()
            mock_complete.assert_called_once()
            args, _ = mock_complete.call_args
            assert args[1] > 0
            assert args[2] > 0

    @pytest.mark.asyncio
    async def test_long_weekend_sweep_passes_return_date(self):
        """_scan_route should be called with return_date and route_suffix."""
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[]) as mock_scan,
            patch("app.scheduler_jobs._start_job_run") as mock_start,
        ):
            from app.scheduler_jobs import run_long_weekend_sweep

            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_long_weekend_sweep()

            assert mock_scan.call_count > 0
            for call_args in mock_scan.call_args_list:
                kwargs = call_args[1]
                assert "return_date" in kwargs
                assert kwargs["return_date"] is not None
                assert kwargs["route_suffix"] == "-long-weekend"
