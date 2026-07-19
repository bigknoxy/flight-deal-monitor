"""Test scheduler job store separation from app database."""

import os

from app.config import config


class TestSchedulerJobstoreSeparation:
    """Verify scheduler uses dedicated job store database."""

    def test_jobstore_url_differs_from_app_database(self):
        """Job store URL must point to a different file than app database."""
        from app.scheduler import jobstores

        jobstore = jobstores["default"]
        # SQLAlchemyJobStore creates an engine with the URL
        jobstore_url = str(jobstore.engine.url)

        # The jobstore URL should contain "flight_deals_jobs" and NOT "flight_deals.db"
        assert "flight_deals_jobs" in jobstore_url, (
            f"Job store URL should contain 'flight_deals_jobs': {jobstore_url}"
        )
        assert "flight_deals.db" not in jobstore_url, (
            f"Job store URL should NOT contain 'flight_deals.db': {jobstore_url}"
        )

        # Also verify config.env.scheduler_jobstore_url differs from database_url
        assert config.env.scheduler_jobstore_url != config.env.database_url, (
            "scheduler_jobstore_url should differ from database_url"
        )

    def test_jobstore_uses_scheduler_jobstore_url(self):
        """Job store should use scheduler_jobstore_url config value."""
        from app.scheduler import jobstores

        jobstore = jobstores["default"]
        jobstore_url = str(jobstore.engine.url)
        expected_url = config.env.scheduler_jobstore_url

        assert jobstore_url == expected_url, (
            f"Job store URL should match config: {jobstore_url} != {expected_url}"
        )

    def test_jobstore_scheduler_py_has_engine_options(self):
        """scheduler.py should construct SQLAlchemyJobStore with engine_options."""
        # Read the scheduler.py source to verify engine_options is present
        with open("app/scheduler.py") as f:
            source = f.read()

        # Verify the jobstores construction includes engine_options
        assert "engine_options" in source, "scheduler.py should have engine_options"
        assert '"timeout": 5' in source, "scheduler.py should have timeout=5 in connect_args"


class TestJobstoreDirectoryCreation:
    """Verify job store directory is created when missing."""

    def test_ensure_jobstore_dir_creates_missing_directory(self, monkeypatch):
        """_ensure_jobstore_dir should create parent directory if missing."""
        # Use relative path format like the actual config (sqlite:///./path)
        temp_db_path = "./new_data/test_jobs.db"
        temp_url = f"sqlite:///{temp_db_path}"

        # Patch the config to use our temp path
        monkeypatch.setattr(config.env, "scheduler_jobstore_url", temp_url)

        # Import the function directly and call it
        from app.scheduler import _ensure_jobstore_dir

        _ensure_jobstore_dir()

        # The directory should have been created under cwd
        expected_dir = "new_data"
        assert os.path.exists(expected_dir), (
            f"Job store directory should be created: {expected_dir}"
        )
        # Cleanup
        os.rmdir(expected_dir)

    def test_ensure_jobstore_dir_handles_existing_directory(self, tmp_path, monkeypatch):
        """_ensure_jobstore_dir should not fail if directory exists."""
        # Create the directory first
        existing_dir = str(tmp_path / "existing_data")
        os.makedirs(existing_dir, exist_ok=True)
        temp_db_path = str(tmp_path / "existing_data" / "test_jobs.db")
        temp_url = f"sqlite:///{temp_db_path}"

        monkeypatch.setattr(config.env, "scheduler_jobstore_url", temp_url)

        from app.scheduler import _ensure_jobstore_dir

        # Should not raise
        _ensure_jobstore_dir()
        assert os.path.exists(existing_dir)

    def test_ensure_jobstore_dir_skips_non_sqlite(self, monkeypatch):
        """_ensure_jobstore_dir should skip for non-SQLite URLs."""
        monkeypatch.setattr(config.env, "scheduler_jobstore_url", "postgresql://localhost/test")

        from app.scheduler import _ensure_jobstore_dir

        # Should not raise for PostgreSQL
        _ensure_jobstore_dir()
