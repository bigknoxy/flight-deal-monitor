"""Test that sweep operations complete within acceptable time bounds."""

import asyncio
import time
from unittest.mock import MagicMock, patch


async def test_regular_sweep_batches_scans():
    """Verify that regular sweep batches scans properly to avoid unbounded duration."""
    from app.scheduler_jobs import run_regular_sweep
    
    with patch("app.scheduler_jobs._start_job_run") as mock_start:
        with patch("app.scheduler_jobs._run_concurrent_sweep") as mock_run:
            with patch("app.scheduler_jobs.AsyncSessionLocal") as mock_session_local:
                mock_session_local.return_value.__aenter__.return_value = MagicMock()
                mock_session_local.return_value.__aexit__.return_value = None
                
                # Mock config values
                with patch("app.scheduler_jobs.config.app.home_airports", ["MCI"]):
                    with patch("app.scheduler_jobs.config.app.destinations", ["LHR"]):
                        with patch("app.scheduler_jobs.config.app.look_ahead_days", 14):  # 2 offsets
                            
                            # Run the sweep - it should complete quickly with batching
                            start = time.time()
                            await run_regular_sweep()
                            elapsed = time.time() - start
                            
                            # With batching, should complete in well under the 30min timeout
                            assert elapsed < 60, f"Sweep took {elapsed:.1f}s, expected < 60s with batching"
                            
                            # Verify _run_concurrent_sweep was called
                            assert mock_run.called, "_run_concurrent_sweep should have been called"


async def test_mistake_sweep_batches_scans():
    """Verify that mistake sweep batches scans properly."""
    from app.scheduler_jobs import run_mistake_sweep
    
    with patch("app.scheduler_jobs._start_job_run") as mock_start:
        with patch("app.scheduler_jobs._run_concurrent_sweep") as mock_run:
            with patch("app.scheduler_jobs.AsyncSessionLocal") as mock_session_local:
                mock_session_local.return_value.__aenter__.return_value = MagicMock()
                mock_session_local.return_value.__aexit__.return_value = None
                
                # Mock config values
                with patch("app.scheduler_jobs.config.app.home_airports", ["MCI"]):
                    with patch("app.scheduler_jobs.config.app.destinations", ["LHR"]):
                        with patch("app.scheduler_jobs.config.app.look_ahead_days", 30):
                            
                            # Run the sweep
                            start = time.time()
                            await run_mistake_sweep()
                            elapsed = time.time() - start
                            
                            # With batching, should complete in well under the 30min timeout
                            assert elapsed < 60, f"Mistake sweep took {elapsed:.1f}s, expected < 60s with batching"
                            
                            # Verify _run_concurrent_sweep was called
                            assert mock_run.called, "_run_concurrent_sweep should have been called"
