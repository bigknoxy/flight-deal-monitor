"""Test Alembic migration setup."""

import pytest
import sqlmodel


class TestAlembicImports:
    """Test that all models are importable by alembic."""

    def test_flight_models_in_metadata(self):
        """FlightDeal and AlertHistory tables must be in SQLModel.metadata."""
        from app.models.flight import AlertHistory, FlightDeal  # noqa: F401

        tables = sqlmodel.SQLModel.metadata.tables
        assert "flightdeal" in tables
        assert "alerthistory" in tables

    def test_job_models_in_metadata(self):
        """JobRun table must be in SQLModel.metadata."""
        from app.models.job import JobRun  # noqa: F401

        tables = sqlmodel.SQLModel.metadata.tables
        assert "jobrun" in tables

    def test_database_url_utility_importable(self):
        """get_async_database_url must be importable from alembic env."""
        from app.utils.database_url import get_async_database_url

        assert get_async_database_url("sqlite://") == "sqlite+aiosqlite://"

    def test_alembic_config_loads(self):
        """Alembic config file must load without errors."""
        pytest.importorskip("alembic.config")
        from alembic.config import Config

        cfg = Config("alembic.ini")
        assert cfg.get_main_option("script_location") == "alembic"

    @pytest.mark.skip(reason="Requires database connection")
    def test_alembic_can_generate_migration(self):
        """Alembic can generate a migration (opt-in, requires database)."""
        from alembic import command  # noqa: I001
        from alembic.config import Config

        cfg = Config("alembic.ini")
        command.revision(cfg, autogenerate=True, message="test_migration")
