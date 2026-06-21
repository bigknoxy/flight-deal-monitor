"""Test database URL parsing utility."""

import pytest

from app.utils.database_url import get_async_database_url


class TestGetAsyncDatabaseUrl:
    """Test get_async_database_url URL conversion."""

    def test_sqlite_conversion(self):
        """sqlite:///path -> sqlite+aiosqlite:///path"""
        url = get_async_database_url("sqlite:///./test.db")
        assert url == "sqlite+aiosqlite:///./test.db"

    def test_postgresql_conversion(self):
        """postgresql:// -> postgresql+asyncpg://"""
        url = get_async_database_url("postgresql://user:pass@localhost:5432/db")
        assert url == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_postgres_short_form_conversion(self):
        """postgres:// -> postgresql+asyncpg://"""
        url = get_async_database_url("postgres://user:pass@localhost:5432/db")
        assert url == "postgresql+asyncpg://user:pass@localhost:5432/db"

    def test_already_async_sqlite_unchanged(self):
        """Already async SQLite URL should be unchanged."""
        url = get_async_database_url("sqlite+aiosqlite:///./test.db")
        assert url == "sqlite+aiosqlite:///./test.db"

    def test_already_async_postgresql_unchanged(self):
        """Already async PostgreSQL URL should be unchanged."""
        url = get_async_database_url("postgresql+asyncpg://user:pass@localhost/db")
        assert url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_empty_string_returns_empty(self):
        """Empty string should be returned unchanged."""
        url = get_async_database_url("")
        assert url == ""

    def test_no_scheme_raises_value_error(self):
        """URL with no scheme should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported database scheme"):
            get_async_database_url("/path/to/db")

    def test_postgresql_with_query_params(self):
        """Query parameters should be preserved."""
        url = get_async_database_url(
            "postgresql://user:pass@host:5432/db?sslmode=require"
        )
        assert url == "postgresql+asyncpg://user:pass@host:5432/db?sslmode=require"

    def test_sqlite_absolute_path(self):
        """Absolute SQLite paths should convert correctly."""
        url = get_async_database_url("sqlite:////absolute/path/to/db.sqlite")
        assert url == "sqlite+aiosqlite:////absolute/path/to/db.sqlite"

    def test_sqlite_in_memory(self):
        """In-memory SQLite should convert correctly."""
        url = get_async_database_url("sqlite://")
        assert url == "sqlite+aiosqlite://"

    def test_postgresql_with_special_chars_in_password(self):
        """Special characters in credentials should be preserved."""
        url = get_async_database_url(
            "postgresql://user:p%40ss@host:5432/db"
        )
        assert url == "postgresql+asyncpg://user:p%40ss@host:5432/db"
