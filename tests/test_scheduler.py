"""Test scheduler module — start, shutdown, status, job setup."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.scheduler import (
    get_scheduler_status,
    scheduler,
    setup_jobs,
    shutdown_scheduler,
    start_scheduler,
)


class TestSchedulerLifecycle:
    """Test scheduler start/shutdown with mocked APScheduler."""

    def test_start_scheduler_success(self):
        with patch.object(scheduler, "start") as mock_start:
            start_scheduler()
            mock_start.assert_called_once()

    def test_start_scheduler_raises_on_failure(self):
        with patch.object(scheduler, "start", side_effect=Exception("start failed")):
            with pytest.raises(Exception, match="start failed"):
                start_scheduler()

    def test_shutdown_scheduler_success(self):
        with patch.object(scheduler, "shutdown") as mock_shutdown:
            shutdown_scheduler()
            mock_shutdown.assert_called_once_with(wait=True)

    def test_shutdown_scheduler_handles_error(self):
        """Shutdown must not raise — it logs and swallows errors."""
        with patch.object(scheduler, "shutdown", side_effect=Exception("shutdown failed")):
            shutdown_scheduler()


class TestSchedulerStatus:
    """Test get_scheduler_status when different scheduler states."""

    def _make_status_test(self, running: bool, jobs: list):
        """Helper: mock the entire scheduler module for status tests."""
        mock_jobs = []
        for j in jobs:
            m = MagicMock()
            m.id = j.get("id")
            m.name = j.get("name")
            m.next_run_time = j.get("next_run_time")
            mock_jobs.append(m)

        with patch("app.scheduler.scheduler") as mock_sched:
            mock_sched.running = running
            mock_sched.get_jobs.return_value = mock_jobs
            return get_scheduler_status()

    def test_status_running_with_jobs(self):
        status = self._make_status_test(
            running=True,
            jobs=[
                {"id": "regular_sweep", "name": "Regular Sweep", "next_run_time": None},
                {"id": "mistake_sweep", "name": "Mistake Sweep", "next_run_time": None},
            ],
        )
        assert status["running"] is True
        assert status["job_count"] == 2
        assert len(status["jobs"]) == 2

    def test_status_running_with_no_jobs(self):
        status = self._make_status_test(running=True, jobs=[])
        assert status["running"] is True
        assert status["job_count"] == 0
        assert status["jobs"] == []

    def test_status_not_running(self):
        status = self._make_status_test(running=False, jobs=[])
        assert status["running"] is False
        assert status["job_count"] == 0

    def test_status_job_next_run_none(self):
        status = self._make_status_test(
            running=True,
            jobs=[{"id": "test_job", "name": "Test Job", "next_run_time": None}],
        )
        assert status["jobs"][0]["next_run"] is None

    def test_status_job_with_next_run_time(self):
        from datetime import datetime
        status = self._make_status_test(
            running=True,
            jobs=[{"id": "test_job", "name": "Test Job", "next_run_time": datetime(2024, 6, 1, 12, 0, 0)}],
        )
        assert status["jobs"][0]["next_run"] == "2024-06-01T12:00:00"


class TestSetupJobs:
    """Test that setup_jobs adds both jobs with correct config."""

    def test_setup_jobs_adds_regular_and_mistake(self):
        with patch.object(scheduler, "add_job") as mock_add_job:
            setup_jobs()
            assert mock_add_job.call_count == 2

            call1 = mock_add_job.call_args_list[0]
            assert call1[0][1] == "interval"
            assert call1[1]["id"] == "regular_sweep"

            call2 = mock_add_job.call_args_list[1]
            assert call2[0][1] == "interval"
            assert call2[1]["id"] == "mistake_sweep"

    def test_setup_jobs_replace_existing(self):
        """All jobs must have replace_existing=True."""
        with patch.object(scheduler, "add_job") as mock_add_job:
            setup_jobs()
            for call in mock_add_job.call_args_list:
                assert call[1]["replace_existing"] is True

    def test_setup_jobs_logs_jobs(self):
        """setup_jobs should iterate over scheduler.get_jobs() (line 100)."""
        mock_job = MagicMock()
        mock_job.name = "Test Job"
        mock_job.id = "test"

        with patch.object(scheduler, "add_job") as mock_add_job:
            with patch.object(scheduler, "get_jobs", return_value=[mock_job, mock_job]):
                setup_jobs()
                # get_jobs called after adding jobs (for logging)
                assert scheduler.get_jobs.call_count >= 1


class TestSchedulerConfig:
    """Verify scheduler construction has correct job defaults."""

    def test_job_defaults_coalesce(self):
        assert scheduler._job_defaults["coalesce"] is True
        assert scheduler._job_defaults["max_instances"] == 1
        assert scheduler._job_defaults["misfire_grace_time"] == 300
