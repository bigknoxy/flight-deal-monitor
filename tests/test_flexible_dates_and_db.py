"""Offline unit tests for flexible_dates and database_url utilities."""

import pytest

from app.utils.database_url import get_async_database_url
from app.utils.flexible_dates import expand_date_range, generate_multi_city_routes


class TestExpandDateRange:

    def test_default_range_days(self):
        result = expand_date_range("2025-07-10")
        assert len(result) == 7
        assert result[0] == "2025-07-07"
        assert result[-1] == "2025-07-13"
        assert result[3] == "2025-07-10"

    def test_custom_range_days(self):
        result = expand_date_range("2025-01-01", range_days=1)
        assert result == ["2024-12-31", "2025-01-01", "2025-01-02"]

    def test_range_days_zero(self):
        result = expand_date_range("2025-03-15", range_days=0)
        assert result == ["2025-03-15"]

    def test_count_matches_formula(self):
        for rd in [0, 1, 2, 5, 10]:
            result = expand_date_range("2025-06-01", range_days=rd)
            assert len(result) == 2 * rd + 1

    def test_all_dates_are_weekday_agnostic(self):
        result = expand_date_range("2025-07-13", range_days=2)
        assert result == ["2025-07-11", "2025-07-12", "2025-07-13", "2025-07-14", "2025-07-15"]


class TestGenerateMultiCityRoutes:

    def test_two_destinations(self):
        routes = generate_multi_city_routes("MCI", ["LHR", "CDG"])
        assert len(routes) == 2
        assert ("MCI", "LHR", "CDG") in routes
        assert ("MCI", "CDG", "LHR") in routes

    def test_three_destinations_count(self):
        routes = generate_multi_city_routes("MCI", ["LHR", "CDG", "NRT"])
        assert len(routes) == 6

    def test_home_excluded_from_stop_and_dest(self):
        routes = generate_multi_city_routes("MCI", ["MCI", "LHR", "CDG"])
        for _, stop, dest in routes:
            assert stop != "MCI"
            assert dest != "MCI"

    def test_max_stops_below_two_returns_empty(self):
        assert generate_multi_city_routes("MCI", ["LHR"], max_stops=0) == []
        assert generate_multi_city_routes("MCI", ["LHR"], max_stops=1) == []

    def test_empty_destinations(self):
        assert generate_multi_city_routes("MCI", []) == []

    def test_all_tuples_have_length_three(self):
        routes = generate_multi_city_routes("JFK", ["LAX", "ORD", "MIA", "SFO"])
        for r in routes:
            assert isinstance(r, tuple)
            assert len(r) == 3

    def test_no_duplicate_pairs(self):
        routes = generate_multi_city_routes("ATL", ["DEN", "SEA", "BOS", "PHX"])
        assert len(routes) == len(set(routes))


class TestGetAsyncDatabaseUrl:

    def test_sqlite_relative(self):
        assert get_async_database_url("sqlite:///./app.db") == "sqlite+aiosqlite:///./app.db"

    def test_sqlite_absolute(self):
        assert get_async_database_url("sqlite:////var/data/prod.sqlite") == "sqlite+aiosqlite:////var/data/prod.sqlite"

    def test_sqlite_in_memory(self):
        assert get_async_database_url("sqlite://") == "sqlite+aiosqlite://"

    def test_postgresql_full(self):
        url = "postgresql://admin:s3cret@db.example.com:5432/flightdb"
        assert get_async_database_url(url) == "postgresql+asyncpg://admin:s3cret@db.example.com:5432/flightdb"

    def test_postgres_short_form(self):
        url = "postgres://u:p@localhost/railway"
        assert get_async_database_url(url) == "postgresql+asyncpg://u:p@localhost/railway"

    def test_already_async_sqlite_passthrough(self):
        url = "sqlite+aiosqlite:///cached.db"
        assert get_async_database_url(url) is url

    def test_already_async_postgresql_passthrough(self):
        url = "postgresql+asyncpg://u:p@host/db"
        assert get_async_database_url(url) is url

    def test_empty_string(self):
        assert get_async_database_url("") == ""

    def test_unsupported_scheme_raises(self):
        with pytest.raises(ValueError, match="Unsupported database scheme"):
            get_async_database_url("mysql://root@localhost/mydb")

    def test_query_params_preserved(self):
        url = "postgresql://u:p@h:5432/db?sslmode=require&connect_timeout=10"
        result = get_async_database_url(url)
        assert result == "postgresql+asyncpg://u:p@h:5432/db?sslmode=require&connect_timeout=10"
