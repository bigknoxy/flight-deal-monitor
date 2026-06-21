"""Test flexible dates utility and multi-city route generation."""

import os
import tempfile

import yaml

from app.config import AppConfig
from app.utils.flexible_dates import expand_date_range, generate_multi_city_routes


class TestExpandDateRange:

    def test_basic_range(self):
        """Basic 3-day range each side of target."""
        dates = expand_date_range("2024-06-15", range_days=3)
        assert dates == [
            "2024-06-12",
            "2024-06-13",
            "2024-06-14",
            "2024-06-15",
            "2024-06-16",
            "2024-06-17",
            "2024-06-18",
        ]

    def test_month_boundary(self):
        """Should handle crossing month boundaries correctly."""
        dates = expand_date_range("2024-02-01", range_days=3)
        assert dates == [
            "2024-01-29",
            "2024-01-30",
            "2024-01-31",
            "2024-02-01",
            "2024-02-02",
            "2024-02-03",
            "2024-02-04",
        ]

    def test_year_boundary(self):
        """Should handle crossing year boundaries correctly."""
        dates = expand_date_range("2024-01-01", range_days=3)
        assert dates == [
            "2023-12-29",
            "2023-12-30",
            "2023-12-31",
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
        ]

    def test_range_days_zero(self):
        """With range_days=0, only the target date should be returned."""
        dates = expand_date_range("2024-06-15", range_days=0)
        assert dates == ["2024-06-15"]

    def test_iso_format_output(self):
        """All returned dates must be YYYY-MM-DD format."""
        dates = expand_date_range("2024-12-25", range_days=5)
        for d in dates:
            assert len(d) == 10
            assert d[4] == "-"
            assert d[7] == "-"

    def test_sorted_order(self):
        """Dates must be returned in ascending order."""
        dates = expand_date_range("2024-06-15", range_days=5)
        for i in range(len(dates) - 1):
            assert dates[i] < dates[i + 1]

    def test_leap_year_february(self):
        """Should handle February in a leap year."""
        dates = expand_date_range("2024-02-29", range_days=1)
        assert dates == [
            "2024-02-28",
            "2024-02-29",
            "2024-03-01",
        ]


class TestGenerateMultiCityRoutes:

    def test_basic_routes(self):
        """Should generate all ordered pairs from destinations."""
        routes = generate_multi_city_routes("MCI", ["LHR", "BCN", "DUB"], max_stops=2)
        assert len(routes) == 6
        assert ("MCI", "LHR", "BCN") in routes
        assert ("MCI", "LHR", "DUB") in routes
        assert ("MCI", "BCN", "LHR") in routes
        assert ("MCI", "BCN", "DUB") in routes
        assert ("MCI", "DUB", "LHR") in routes
        assert ("MCI", "DUB", "BCN") in routes

    def test_all_routes_have_home_as_origin(self):
        """Every route must start with the home airport."""
        routes = generate_multi_city_routes("MCI", ["LHR", "BCN", "DUB"])
        for origin, stop, dest in routes:
            assert origin == "MCI"

    def test_stop_not_equal_destination(self):
        """stop and destination must be different airports."""
        routes = generate_multi_city_routes("MCI", ["LHR", "BCN", "DUB"])
        for _, stop, dest in routes:
            assert stop != dest

    def test_no_home_in_stop_or_destination(self):
        """stop and destination must not be the home airport."""
        routes = generate_multi_city_routes("MCI", ["LHR", "BCN", "DUB"])
        for _, stop, dest in routes:
            assert stop != "MCI"
            assert dest != "MCI"

    def test_max_stops_one(self):
        """With max_stops < 2, no valid multi-city routes can be formed."""
        routes = generate_multi_city_routes("MCI", ["LHR", "BCN", "DUB"], max_stops=1)
        assert routes == []

    def test_empty_destinations(self):
        """Empty destination list should produce no routes."""
        routes = generate_multi_city_routes("MCI", [], max_stops=2)
        assert routes == []

    def test_single_destination(self):
        """Single destination cannot form stop-dest pairs."""
        routes = generate_multi_city_routes("MCI", ["LHR"], max_stops=2)
        assert routes == []

    def test_no_duplicate_routes(self):
        """No duplicate (origin, stop, dest) tuples should exist."""
        routes = generate_multi_city_routes("MCI", ["LHR", "BCN", "DUB", "JFK"])
        keys = {(o, s, d) for o, s, d in routes}
        assert len(keys) == len(routes)

    def test_destination_same_as_home_is_excluded(self):
        """Destinations equal to home should not appear in routes."""
        routes = generate_multi_city_routes("MCI", ["MCI", "LHR", "BCN"], max_stops=2)
        for _, stop, dest in routes:
            assert stop != "MCI"
            assert dest != "MCI"


class TestFlexibleDatesConfig:

    def test_default_config_values(self):
        """New config classes should have correct defaults."""
        from app.config import FlexibleDatesConfig, MultiCityConfig

        fd = FlexibleDatesConfig()
        assert fd.enabled is False
        assert fd.range_days == 3

        mc = MultiCityConfig()
        assert mc.enabled is False
        assert mc.max_stops == 2

    def test_config_loaded_from_yaml(self):
        """AppConfig should load flexible_dates and multi_city from YAML."""
        data = {
            "app": {
                "flexible_dates": {
                    "enabled": True,
                    "range_days": 5,
                },
                "multi_city": {
                    "enabled": True,
                    "max_stops": 3,
                },
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.flexible_dates.enabled is True
            assert config.flexible_dates.range_days == 5
            assert config.multi_city.enabled is True
            assert config.multi_city.max_stops == 3
        finally:
            os.unlink(path)

    def test_config_defaults_when_not_in_yaml(self):
        """When YAML has no flexible_dates/multi_city, defaults should apply."""
        data = {"app": {"name": "test"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        try:
            config = AppConfig.from_yaml(path)
            assert config.flexible_dates.enabled is False
            assert config.flexible_dates.range_days == 3
            assert config.multi_city.enabled is False
            assert config.multi_city.max_stops == 2
        finally:
            os.unlink(path)
