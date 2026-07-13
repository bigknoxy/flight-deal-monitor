"""Test sweep functions — run_regular_sweep, run_mistake_sweep lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import config
from app.scheduler_jobs import run_mistake_sweep, run_regular_sweep


class TestRegularSweepLifecycle:
    @pytest.mark.asyncio
    async def test_regular_sweep_with_deals(self):
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
            patch(
                "app.alert_dispatch.telegram_bot.send_alert", return_value="msg_1"
            ) as mock_send,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_regular_sweep()

            mock_send.assert_called()
            mock_complete.assert_called_once()
            args, _ = mock_complete.call_args
            assert args[1] > 0  # deals_detected
            assert args[2] > 0  # alerts_sent

    @pytest.mark.asyncio
    async def test_regular_sweep_with_failed_alert(self):
        """When alert send fails, record shows failed status."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        deal = MagicMock()
        deal.id = 2

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[deal]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
            patch(
                "app.alert_dispatch.telegram_bot.send_alert", return_value=None
            ) as mock_send,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_regular_sweep()

            mock_send.assert_called()
            mock_complete.assert_called_once()
            args, _ = mock_complete.call_args
            assert args[1] > 0  # deals_detected
            assert args[2] == 0  # alerts_sent (failed)

    """Test the top-level regular sweep function with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_regular_sweep_success(self):
        """Run regular sweep through its success path."""
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_regular_sweep()

            mock_start.assert_called_once_with("regular_sweep")
            mock_complete.assert_called_once()
            # No deals found, so complete should have 0 deals / 0 alerts
            mock_complete.assert_called_once_with(mock_job_run, 0, 0)

    @pytest.mark.asyncio
    async def test_regular_sweep_failure(self):
        """When regular sweep fails, _fail_job_run should be called."""
        with (
            patch(
                "app.scheduler_jobs.AsyncSessionLocal", side_effect=Exception("DB down")
            ),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._fail_job_run") as mock_fail,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_regular_sweep()

            mock_fail.assert_called_once()
            error_msg = mock_fail.call_args[0][1]
            assert "DB down" in error_msg


class TestMistakeSweepLifecycle:
    """Test the top-level mistake sweep function."""

    @pytest.mark.asyncio
    async def test_mistake_sweep_success(self):
        """Run mistake sweep with no mistake fares found."""
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_mistake_sweep()

            mock_start.assert_called_once_with("mistake_sweep")
            mock_complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_mistake_sweep_failure(self):
        """When mistake sweep fails, _fail_job_run should be called."""
        with (
            patch(
                "app.scheduler_jobs.AsyncSessionLocal", side_effect=Exception("timeout")
            ),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._fail_job_run") as mock_fail,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_mistake_sweep()

            mock_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_mistake_sweep_with_alerts_sent(self):
        """Mistake sweep should send alerts and record them when telegrams works."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mistake_deal = MagicMock()
        mistake_deal.deal_type = "mistake_fare"
        mistake_deal.id = 42

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[mistake_deal]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
            patch(
                "app.alert_dispatch.telegram_bot.send_alert", return_value="msg_123"
            ) as mock_send,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_mistake_sweep()

            mock_send.assert_called()
            mock_complete.assert_called_once()
            # Every home-airport x destination x 30 days returns the mistake_deal
            expected = len(config.app.home_airports) * len(config.app.destinations) * 30
            args, _ = mock_complete.call_args
            assert args[1] == expected  # deals_detected
            assert args[2] == expected  # alerts_sent

    @pytest.mark.asyncio
    async def test_mistake_sweep_with_alert_failure(self):
        """When telegram fails, alert records should show 'failed' status."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        mistake_deal = MagicMock()
        mistake_deal.deal_type = "mistake_fare"
        mistake_deal.id = 42

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[mistake_deal]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
            patch(
                "app.alert_dispatch.telegram_bot.send_alert", return_value=None
            ) as mock_send,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_mistake_sweep()

            mock_send.assert_called()
            mock_complete.assert_called_once()
            # deals_detected = every home x dest x 30 days; alerts_sent=0 (send fails)
            expected = len(config.app.home_airports) * len(config.app.destinations) * 30
            args, _ = mock_complete.call_args
            assert args[1] == expected  # deals_detected
            assert args[2] == 0  # alerts_sent

    @pytest.mark.asyncio
    async def test_mistake_sweep_filters_only_mistake_fares(self):
        """Mistake sweep should only alert on mistake_fare type deals."""
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        flash_deal = MagicMock()
        flash_deal.deal_type = "flash_sale"

        with (
            patch("app.scheduler_jobs.AsyncSessionLocal", return_value=mock_session),
            patch("app.scheduler_jobs._scan_route", return_value=[flash_deal]),
            patch("app.scheduler_jobs._start_job_run") as mock_start,
            patch("app.scheduler_jobs._complete_job_run") as mock_complete,
            patch("app.alert_dispatch.telegram_bot") as mock_bot,
        ):
            mock_job_run = MagicMock()
            mock_start.return_value = mock_job_run

            await run_mistake_sweep()

            # flash_sale should NOT trigger an alert
            mock_bot.send_alert.assert_not_called()
            mock_complete.assert_called_once()
