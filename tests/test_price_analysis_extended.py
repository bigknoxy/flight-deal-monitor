"""Extended price analysis tests — edge cases for calculate_median_price, detect_deal boundaries."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.flight import PriceObservation
from app.utils.price_analysis import (
    apply_route_multiplier,
    calculate_median_price,
    detect_deal,
    generate_route_id,
    get_route_type,
    record_price_observations,
)


class TestCalculateMedianPrice:
    """Tests for async DB-based median price calculation."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_history(self):
        """Cold-start: with no observations the route has no baseline, so None."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR")
        assert median is None

    @pytest.mark.asyncio
    async def test_median_single_value(self):
        """Single price = the median."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(300.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR", days_back=30, min_samples=1)
        assert median == 300.0

    @pytest.mark.asyncio
    async def test_median_even_count(self):
        """Even number of prices: median is average of two middle values."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(100.0,), (200.0,), (300.0,), (400.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR", min_samples=1)
        assert median == 250.0  # (200 + 300) / 2

    @pytest.mark.asyncio
    async def test_median_odd_count(self):
        """Odd number of prices: median is the middle value."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(100.0,), (200.0,), (300.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR", min_samples=1)
        assert median == 200.0

    @pytest.mark.asyncio
    async def test_median_unsorted_input(self):
        """Even if DB returns unsorted, median calculation sorts internally."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(500.0,), (100.0,), (300.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR", min_samples=1)
        assert median == 300.0


class TestDetectDealBoundaries:
    """Boundary value analysis for detect_deal thresholds."""

    def test_mistake_fare_exact_threshold(self):
        """Exactly 70% off = mistake fare."""
        is_deal, deal_type = detect_deal(150.0, 500.0)  # (500-150)/500 = 0.70
        assert is_deal is True
        assert deal_type == "mistake_fare"

    def test_flash_sale_exact_threshold(self):
        """Exactly 50% off = flash sale."""
        is_deal, deal_type = detect_deal(250.0, 500.0)  # (500-250)/500 = 0.50
        assert is_deal is True
        assert deal_type == "flash_sale"

    def test_barely_not_a_deal(self):
        """49% off is not a deal."""
        is_deal, deal_type = detect_deal(255.0, 500.0)  # (500-255)/500 = 0.49
        assert is_deal is False
        assert deal_type is None

    def test_mistake_fare_borderline(self):
        """69.9% off = deep_flash, not mistake fare."""
        # (500 - x) / 500 = 0.699  =>  x = 150.5
        is_deal, deal_type = detect_deal(150.5, 500.0)
        assert is_deal is True
        assert deal_type == "deep_flash"

    def test_deal_with_very_high_price(self):
        """10x median price, not a deal."""
        is_deal, deal_type = detect_deal(5000.0, 500.0)
        assert is_deal is False
        assert deal_type is None

    def test_deal_with_median_zero(self):
        """If median is 0, division by zero avoided."""
        is_deal, deal_type = detect_deal(100.0, 0.0)
        # current_price (100) >= median (0), so returns False
        assert is_deal is False
        assert deal_type is None

    def test_deal_exact_zero_current_price(self):
        """Current price is 0 — should be detected as deal (but filtered by min_price_usd upstream)."""
        is_deal, deal_type = detect_deal(0.0, 500.0)
        assert is_deal is True
        assert deal_type == "mistake_fare"


class TestCalculatePriceDropExtended:
    """Extended edge cases for calculate_price_drop."""

    def test_price_drop_negative(self):
        """Current price higher than median = negative drop (but function doesn't guard)."""
        from app.utils import calculate_price_drop
        drop = calculate_price_drop(600.0, 500.0)
        assert drop == -20.0

    def test_price_drop_exact_zero(self):
        from app.utils import calculate_price_drop
        drop = calculate_price_drop(500.0, 500.0)
        assert drop == 0.0

    def test_price_drop_very_small_median(self):
        """When median is very small, the drop can be extremely large (negative)."""
        from app.utils import calculate_price_drop
        drop = calculate_price_drop(1.0, 0.01)
        # ((0.01 - 1.0) / 0.01) * 100 = -9900
        assert drop == -9900.0


class TestGetRouteType:
    """Route classification tests."""

    def test_get_route_type_domestic(self):
        assert get_route_type("JFK", "LAX") == "domestic"

    def test_get_route_type_transatlantic(self):
        assert get_route_type("JFK", "LHR") == "transatlantic"

    def test_get_route_type_transpacific(self):
        assert get_route_type("SFO", "NRT") == "transpacific"

    def test_get_route_type_latin_america(self):
        assert get_route_type("MIA", "SJO") == "latin_america"

    def test_get_route_type_europe(self):
        assert get_route_type("CDG", "FRA") == "europe"

    def test_get_route_type_reverse_transatlantic(self):
        assert get_route_type("LHR", "JFK") == "transatlantic"

    def test_get_route_type_reverse_transpacific(self):
        assert get_route_type("NRT", "LAX") == "transpacific"

    def test_get_route_type_reverse_latin_america(self):
        assert get_route_type("SJO", "MIA") == "latin_america"

    def test_get_route_type_reverse_fallback(self):
        assert get_route_type("LHR", "CDG") == "europe"

    def test_get_route_type_fallback_domestic(self):
        assert get_route_type("SYD", "JFK") == "domestic"


class TestApplyRouteMultiplier:
    """Route multiplier application tests."""

    def test_apply_route_multiplier_domestic(self):
        result = apply_route_multiplier(500.0, "JFK", "LAX")
        assert result == 500.0

    def test_apply_route_multiplier_transatlantic(self):
        result = apply_route_multiplier(500.0, "JFK", "LHR")
        assert result == 400.0

    def test_apply_route_multiplier_transpacific(self):
        result = apply_route_multiplier(500.0, "NRT", "LAX")
        assert result == 350.0


class TestDetectDealWithRouteMultiplier:
    """detect_deal with optional origin/destination parameters."""

    def test_detect_deal_with_route_multiplier(self):
        is_deal, deal_type = detect_deal(120.0, 400.0, "JFK", "LHR")
        assert is_deal is True
        assert deal_type == "flash_sale"

    def test_detect_deal_without_route_multiplier(self):
        is_deal, deal_type = detect_deal(250.0, 500.0)
        assert is_deal is True
        assert deal_type == "flash_sale"


class TestRecordPriceObservations:
    """Tests for accumulating a real market baseline (B21)."""

    @pytest.mark.asyncio
    async def test_records_valid_prices_only(self):
        """Record only positive prices above the floor; skip junk/invalid."""
        from app.utils.price_analysis import record_price_observations

        mock_session = AsyncMock()
        mock_session.add_all = MagicMock()

        flights = [
            {"validatingAirlineCodes": ["AA"], "price": {"total": "300.00"}},
            {"validatingAirlineCodes": ["DL"], "price": {"total": "0"}},  # below floor
            {"validatingAirlineCodes": ["UA"], "price": {"total": "not-a-number"}},  # invalid
        ]

        n = await record_price_observations(
            mock_session, "MCI", "LHR", "2024-06-01", flights, min_price_usd=100.0
        )
        assert n == 1
        mock_session.add_all.assert_called_once()


class TestTripTypeDiscriminator:
    """Tier 1: trip_type field threaded through route IDs, medians, and observations."""

    def test_generate_route_id_differs_by_trip_type(self):
        """Same args but different trip_type must produce different hashes."""
        hash_ow = generate_route_id("MCI", "LHR", "2024-06-01", "BA", trip_type="one_way")
        hash_rt = generate_route_id("MCI", "LHR", "2024-06-01", "BA", trip_type="round_trip")
        assert hash_ow != hash_rt

    def test_generate_route_id_with_suffix_and_trip_type(self):
        """Suffix and trip_type combine correctly."""
        h1 = generate_route_id("MCI", "LHR", "2024-06-01", "BA", suffix="-long-weekend", trip_type="one_way")
        h2 = generate_route_id("MCI", "LHR", "2024-06-01", "BA", suffix="-long-weekend", trip_type="round_trip")
        assert h1 != h2

    @pytest.mark.asyncio
    async def test_calculate_median_price_scoped_by_trip_type(self):
        """calculate_median_price filters by trip_type — only matching rows used."""
        mock_session = AsyncMock()

        # Simulate the DB returning only one_way prices (as if the WHERE clause worked)
        mock_result = MagicMock()
        mock_result.all.return_value = [(200.0,), (200.0,), (200.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(
            mock_session, "MCI", "LHR", days_back=30, min_samples=1, trip_type="one_way"
        )
        assert median == 200.0

    @pytest.mark.asyncio
    async def test_record_price_observations_sets_trip_type(self):
        """record_price_observations must set trip_type on each PriceObservation row."""
        mock_session = AsyncMock()
        mock_session.add_all = MagicMock()

        flights = [
            {"validatingAirlineCodes": ["BA"], "price": {"total": "300.00"}},
            {"validatingAirlineCodes": ["DL"], "price": {"total": "400.00"}},
        ]

        n = await record_price_observations(
            mock_session, "MCI", "LHR", "2024-06-01", flights,
            trip_type="round_trip",
        )
        assert n == 2
        mock_session.add_all.assert_called_once()

        # Inspect the rows passed to add_all
        call_args = mock_session.add_all.call_args[0][0]
        assert len(call_args) == 2
        for row in call_args:
            assert isinstance(row, PriceObservation)
            assert row.trip_type == "round_trip"

    @pytest.mark.asyncio
    async def test_record_price_observations_default_one_way(self):
        """Default trip_type is one_way when not specified."""
        mock_session = AsyncMock()
        mock_session.add_all = MagicMock()

        flights = [
            {"validatingAirlineCodes": ["AA"], "price": {"total": "150.00"}},
        ]

        await record_price_observations(
            mock_session, "MCI", "LHR", "2024-06-01", flights,
        )

        call_args = mock_session.add_all.call_args[0][0]
        assert call_args[0].trip_type == "one_way"


class TestMLFeaturePrecomputation:
    """ML features pre-computed at PriceObservation write time (swyx rec #1)."""

    @pytest.mark.asyncio
    async def test_ml_features_populated_for_valid_date(self):
        """days_until_departure, departure_month, day_of_week, bucket set."""
        from datetime import datetime, timedelta

        from app.utils.price_analysis import record_price_observations

        mock_session = AsyncMock()
        mock_session.add_all = MagicMock()

        future = (datetime.utcnow() + timedelta(days=45)).strftime("%Y-%m-%d")
        flights = [{"validatingAirlineCodes": ["AA"], "price": {"total": "300.00"}}]

        await record_price_observations(mock_session, "MCI", "LHR", future, flights)

        row: PriceObservation = mock_session.add_all.call_args[0][0][0]
        assert row.days_until_departure is not None
        assert 44 <= row.days_until_departure <= 46
        assert row.departure_month == int(future.split("-")[1])
        assert row.departure_day_of_week is not None
        assert row.booking_window_bucket == "22-60d"

    @pytest.mark.asyncio
    async def test_ml_features_bucket_boundaries(self):
        """Booking window buckets: 0-7d, 8-21d, 22-60d, 61+d."""
        from datetime import datetime, timedelta

        from app.utils.price_analysis import record_price_observations

        for days, expected_bucket in [
            (3, "0-7d"),
            (14, "8-21d"),
            (45, "22-60d"),
            (90, "61+d"),
        ]:
            mock_session = AsyncMock()
            mock_session.add_all = MagicMock()
            future = (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d")
            flights = [{"validatingAirlineCodes": ["AA"], "price": {"total": "200.00"}}]
            await record_price_observations(mock_session, "MCI", "LHR", future, flights)
            row = mock_session.add_all.call_args[0][0][0]
            assert row.booking_window_bucket == expected_bucket, (
                f"days={days} expected {expected_bucket} got {row.booking_window_bucket}"
            )

    @pytest.mark.asyncio
    async def test_ml_features_none_for_invalid_date(self):
        """Invalid departure_date → ML features are None, row still created."""
        from app.utils.price_analysis import record_price_observations

        mock_session = AsyncMock()
        mock_session.add_all = MagicMock()

        flights = [{"validatingAirlineCodes": ["AA"], "price": {"total": "300.00"}}]
        await record_price_observations(
            mock_session, "MCI", "LHR", "not-a-date", flights
        )

        row = mock_session.add_all.call_args[0][0][0]
        assert row.days_until_departure is None
        assert row.departure_month is None
        assert row.departure_day_of_week is None
        assert row.booking_window_bucket is None
