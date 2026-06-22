"""Extended price analysis tests — edge cases for calculate_median_price, detect_deal boundaries."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.price_analysis import (
    apply_route_multiplier,
    calculate_median_price,
    detect_deal,
    get_route_type,
)


class TestCalculateMedianPrice:
    """Tests for async DB-based median price calculation."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_history(self):
        """When no price history exists, must return None (caller uses search results as baseline)."""
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

        median = await calculate_median_price(mock_session, "MCI", "LHR", days_back=30)
        assert median == 300.0

    @pytest.mark.asyncio
    async def test_median_even_count(self):
        """Even number of prices: median is average of two middle values."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(100.0,), (200.0,), (300.0,), (400.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR")
        assert median == 250.0  # (200 + 300) / 2

    @pytest.mark.asyncio
    async def test_median_odd_count(self):
        """Odd number of prices: median is the middle value."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(100.0,), (200.0,), (300.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR")
        assert median == 200.0

    @pytest.mark.asyncio
    async def test_median_unsorted_input(self):
        """Even if DB returns unsorted, median calculation sorts internally."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [(500.0,), (100.0,), (300.0,)]
        mock_session.execute.return_value = mock_result

        median = await calculate_median_price(mock_session, "MCI", "LHR")
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
