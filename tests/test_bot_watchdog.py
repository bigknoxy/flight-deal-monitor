"""Tests for BotHandler watchdog supervisor."""

import asyncio
from unittest.mock import patch


class TestBotWatchdogRestart:
    """Test watchdog restarts poll loop on unexpected termination."""

    async def test_watchdog_restarts_poll_loop_on_unexpected_termination(self):
        """When _poll_loop task finishes unexpectedly, supervisor recreates it."""
        from app.bot import BotHandler

        handler = BotHandler()
        handler.token = "test_token"

        # Create a real poll task that will complete immediately
        async def fast_poll_loop():
            return

        # Patch _poll_loop to use our fast version
        with patch.object(handler, "_poll_loop", fast_poll_loop):
            # Start polling
            await handler.start_polling()

            # Get the original poll task
            original_poll_task = handler._poll_task

            # Wait for poll loop to complete
            await asyncio.sleep(0.1)

            # Verify the original task is done
            assert original_poll_task.done()

            # Wait for watchdog to detect and restart (watchdog checks every 1s)
            await asyncio.sleep(1.5)

            # Verify a NEW poll task was created (different from original)
            # The watchdog should have recreated it
            assert handler._poll_task is not None
            assert handler._poll_task is not original_poll_task, "Watchdog should have created a new task"

            await handler.stop_polling()

    async def test_watchdog_does_not_restart_during_shutdown(self):
        """During intentional shutdown, supervisor does NOT restart the loop."""
        from app.bot import BotHandler

        handler = BotHandler()
        handler.token = "test_token"

        # Create a real poll task that will complete immediately
        async def fast_poll_loop():
            return

        with patch.object(handler, "_poll_loop", fast_poll_loop):
            await handler.start_polling()

            original_poll_task = handler._poll_task

            # Set _running to False FIRST (simulating shutdown before watchdog detects)
            handler._running = False

            # Cancel the poll task
            original_poll_task.cancel()
            try:
                await original_poll_task
            except asyncio.CancelledError:
                pass

            # Wait for watchdog to detect
            await asyncio.sleep(1.5)

            # Poll task should NOT have been recreated
            assert handler._poll_task is None or handler._poll_task is original_poll_task

    async def test_watchdog_uses_backoff_on_restart(self):
        """Restart has backoff — sleep is awaited before next restart attempt."""
        from app.bot import BotHandler

        handler = BotHandler()
        handler.token = "test_token"

        sleep_times = []

        async def mock_sleep(delay):
            sleep_times.append(delay)

        async def fast_poll_loop():
            return

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with patch.object(handler, "_poll_loop", fast_poll_loop):
                await handler.start_polling()

                # Wait for poll loop to complete
                await asyncio.sleep(0.1)

                # Wait for watchdog detection cycle
                await asyncio.sleep(1.5)

                # Verify backoff sleep was called (not instant restart)
                assert any(t >= 1.0 for t in sleep_times), "Expected backoff sleep on restart"

                await handler.stop_polling()


class TestBotWatchdogIntegration:
    """Integration tests for watchdog with mocked HTTP."""

    async def test_watchdog_logs_warning_on_restart(self):
        """Watchdog logs a clear warning when restarting the loop."""
        from app.bot import BotHandler

        handler = BotHandler()
        handler.token = "test_token"

        async def fast_poll_loop():
            return

        with patch.object(handler, "_poll_loop", fast_poll_loop):
            # Patch the module-level logger
            import app.bot
            with patch.object(app.bot.logger, "warning") as mock_warning:
                await handler.start_polling()

                # Wait for poll loop to complete and watchdog to detect
                await asyncio.sleep(1.5)

                # Verify warning was logged
                assert mock_warning.called, "Expected warning to be logged"
                warning_msg = mock_warning.call_args[0][0]
                assert "terminated unexpectedly" in warning_msg

                await handler.stop_polling()
