"""Test the FastAPI lifespan function directly."""

from unittest.mock import AsyncMock, patch

import pytest


class TestLifespan:
    """Test startup and shutdown lifecycle of the application."""

    @pytest.mark.asyncio
    async def test_lifespan_startup_runs_init(self):
        """Lifespan startup must init DB, test Telegram, setup + start scheduler."""
        from app.main import lifespan

        with (
            patch("app.main.init_db") as mock_init,
            patch("app.main.telegram_bot.test_connection", return_value=True) as mock_telegram,
            patch("app.main.setup_jobs") as mock_setup,
            patch("app.main.start_scheduler") as mock_start,
            patch("app.main.shutdown_scheduler") as mock_shutdown,
            patch("app.main.close_db") as mock_close,
        ):
            async with lifespan(None):
                # Inside lifespan — verify startup ran
                mock_init.assert_called_once()
                mock_telegram.assert_called_once()
                mock_setup.assert_called_once()
                mock_start.assert_called_once()

            # After exiting — verify shutdown ran
            mock_shutdown.assert_called_once()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_cleans_up_properly(self):
        """After successful startup, shutdown must clean up resources."""
        from app.main import lifespan

        with (
            patch("app.main.init_db") as mock_init,
            patch("app.main.telegram_bot.test_connection", return_value=True),
            patch("app.main.setup_jobs"),
            patch("app.main.start_scheduler"),
            patch("app.main.shutdown_scheduler") as mock_shutdown,
            patch("app.main.close_db") as mock_close,
        ):
            async with lifespan(None):
                pass

            mock_shutdown.assert_called_once()
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_and_close_directly(self):
        """verify shutdown_scheduler and close_db can be called independently."""
        import app.main
        with (
            patch.object(app.main, "shutdown_scheduler") as mock_shutdown,
            patch.object(app.main, "close_db") as mock_close,
        ):
            app.main.shutdown_scheduler()
            await app.main.close_db()

            mock_shutdown.assert_called_once()
            mock_close.assert_called_once()
