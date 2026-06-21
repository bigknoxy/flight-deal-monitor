"""Test price history API and utility functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.price_analysis import get_price_history


def _mock_row(date: str, median_price: float, lowest_price: float, sample_count: int) -> MagicMock:
    """Create a mock DB row with labeled column attributes."""
    row = MagicMock()
    row.date = date
    row.median_price = median_price
    row.lowest_price = lowest_price
    row.sample_count = sample_count
    return row


class TestGetPriceHistory:
    """Tests for the get_price_history utility function."""

    @pytest.mark.asyncio
    async def test_empty_history(self):
        """No deals for route returns empty history with flat trend."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        assert result["route"] == "MCI-LHR"
        assert result["days"] == 90
        assert result["data_points"] == 0
        assert result["history"] == []
        assert result["current_median"] is None
        assert result["trend"] == "flat"
        assert result["trend_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_single_day(self):
        """Single day of data returns flat trend."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 500.0, 350.0, 8),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        assert result["route"] == "MCI-LHR"
        assert result["data_points"] == 1
        assert len(result["history"]) == 1
        assert result["history"][0]["date"] == "2026-06-01"
        assert result["history"][0]["median_price"] == 500.0
        assert result["history"][0]["lowest_price"] == 350.0
        assert result["history"][0]["sample_count"] == 8
        assert result["current_median"] == 500.0
        assert result["trend"] == "flat"
        assert result["trend_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_multiple_days(self):
        """Multiple days returns correctly shaped history."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 500.0, 400.0, 5),
            _mock_row("2026-06-02", 480.0, 380.0, 7),
            _mock_row("2026-06-03", 450.0, 350.0, 6),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        assert result["data_points"] == 3
        assert len(result["history"]) == 3
        assert result["current_median"] == 450.0
        assert result["history"][0]["date"] == "2026-06-01"
        assert result["history"][1]["date"] == "2026-06-02"
        assert result["history"][2]["date"] == "2026-06-03"

    @pytest.mark.asyncio
    async def test_trend_down(self):
        """Downward price trend is detected correctly."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # First half avg = (500 + 480) / 2 = 490, Second half avg = (450 + 420) / 2 = 435
        # trend_percent = (435 - 490) / 490 * 100 ≈ -11.22
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 500.0, 400.0, 5),
            _mock_row("2026-06-02", 480.0, 380.0, 7),
            _mock_row("2026-06-03", 450.0, 350.0, 6),
            _mock_row("2026-06-04", 420.0, 320.0, 8),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        assert result["trend"] == "down"
        assert result["trend_percent"] < -5

    @pytest.mark.asyncio
    async def test_trend_up(self):
        """Upward price trend is detected correctly."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # First half avg = (400 + 420) / 2 = 410, Second half avg = (480 + 500) / 2 = 490
        # trend_percent = (490 - 410) / 410 * 100 ≈ 19.51
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 400.0, 350.0, 5),
            _mock_row("2026-06-02", 420.0, 360.0, 7),
            _mock_row("2026-06-03", 480.0, 400.0, 6),
            _mock_row("2026-06-04", 500.0, 420.0, 8),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        assert result["trend"] == "up"
        assert result["trend_percent"] > 5

    @pytest.mark.asyncio
    async def test_trend_flat(self):
        """Flat price trend is detected correctly."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        # All prices within threshold of each other
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 500.0, 450.0, 5),
            _mock_row("2026-06-02", 505.0, 455.0, 7),
            _mock_row("2026-06-03", 498.0, 448.0, 6),
            _mock_row("2026-06-04", 502.0, 452.0, 8),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        assert result["trend"] == "flat"

    @pytest.mark.asyncio
    async def test_different_route_filtering(self):
        """History is filtered by origin and destination."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 800.0, 600.0, 3),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "JFK", "NRT", days=30)

        assert result["route"] == "JFK-NRT"
        assert result["days"] == 30
        assert result["data_points"] == 1

    @pytest.mark.asyncio
    async def test_history_order(self):
        """History is returned in chronological order."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            _mock_row("2026-06-01", 500.0, 400.0, 5),
            _mock_row("2026-06-02", 480.0, 380.0, 7),
            _mock_row("2026-06-03", 450.0, 350.0, 6),
        ]
        mock_session.execute.return_value = mock_result

        result = await get_price_history(mock_session, "MCI", "LHR", days=90)

        dates = [h["date"] for h in result["history"]]
        assert dates == sorted(dates)


@pytest.fixture
async def client():
    """Create async test client without lifespan events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestPriceHistoryEndpoint:
    """Tests for the GET /deals/history API endpoint."""

    @pytest.mark.asyncio
    async def test_history_endpoint_returns_200(self, client):
        """API returns 200 with correct response shape."""
        mock_history = {
            "route": "MCI-LHR",
            "days": 90,
            "data_points": 3,
            "history": [
                {"date": "2026-06-01", "median_price": 500.0, "lowest_price": 400.0, "sample_count": 5},
                {"date": "2026-06-02", "median_price": 480.0, "lowest_price": 380.0, "sample_count": 7},
                {"date": "2026-06-03", "median_price": 450.0, "lowest_price": 350.0, "sample_count": 6},
            ],
            "current_median": 450.0,
            "trend": "down",
            "trend_percent": -10.0,
        }
        with patch("app.main.get_price_history", return_value=mock_history):
            response = await client.get("/deals/history?origin=MCI&destination=LHR&days=90")

        assert response.status_code == 200
        data = response.json()
        assert data["route"] == "MCI-LHR"
        assert data["days"] == 90
        assert data["data_points"] == 3
        assert len(data["history"]) == 3
        assert data["current_median"] == 450.0
        assert data["trend"] == "down"
        assert data["trend_percent"] == -10.0
        assert data["history"][0]["date"] == "2026-06-01"
        assert data["history"][0]["median_price"] == 500.0
        assert data["history"][0]["lowest_price"] == 400.0
        assert data["history"][0]["sample_count"] == 5

    @pytest.mark.asyncio
    async def test_history_endpoint_default_days(self, client):
        """API uses default days=90 when not specified."""
        mock_history = {
            "route": "MCI-LHR",
            "days": 90,
            "data_points": 0,
            "history": [],
            "current_median": None,
            "trend": "flat",
            "trend_percent": 0.0,
        }
        with patch("app.main.get_price_history", return_value=mock_history):
            response = await client.get("/deals/history?origin=MCI&destination=LHR")

        assert response.status_code == 200
        data = response.json()
        assert data["days"] == 90

    @pytest.mark.asyncio
    async def test_history_endpoint_missing_origin(self, client):
        """Missing required origin param returns 422."""
        response = await client.get("/deals/history?destination=LHR")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_history_endpoint_missing_destination(self, client):
        """Missing required destination param returns 422."""
        response = await client.get("/deals/history?origin=MCI")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_history_endpoint_missing_all_params(self, client):
        """Missing all required params returns 422."""
        response = await client.get("/deals/history")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_history_endpoint_uppercase_conversion(self, client):
        """Params are uppercased before passing to get_price_history."""
        mock_history = {
            "route": "MCI-LHR",
            "days": 90,
            "data_points": 0,
            "history": [],
            "current_median": None,
            "trend": "flat",
            "trend_percent": 0.0,
        }
        with patch("app.main.get_price_history", return_value=mock_history) as mock_fn:
            response = await client.get("/deals/history?origin=mci&destination=lhr&days=90")

        assert response.status_code == 200
        mock_fn.assert_called_once()
        args, _ = mock_fn.call_args
        # args[1] is origin, args[2] is destination
        assert args[1] == "MCI"
        assert args[2] == "LHR"

    @pytest.mark.asyncio
    async def test_history_endpoint_empty_result(self, client):
        """API returns empty history correctly."""
        mock_history = {
            "route": "MCI-LHR",
            "days": 90,
            "data_points": 0,
            "history": [],
            "current_median": None,
            "trend": "flat",
            "trend_percent": 0.0,
        }
        with patch("app.main.get_price_history", return_value=mock_history):
            response = await client.get("/deals/history?origin=MCI&destination=LHR&days=90")

        assert response.status_code == 200
        data = response.json()
        assert data["data_points"] == 0
        assert data["history"] == []
        assert data["current_median"] is None
