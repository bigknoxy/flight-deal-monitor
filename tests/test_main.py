"""Test FastAPI application endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Create async test client without lifespan events (to avoid DB init)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRootEndpoint:

    @pytest.mark.asyncio
    async def test_root_redirects_to_dashboard(self, client):
        response = await client.get("/", follow_redirects=False)
        assert response.status_code in (302, 303, 307)
        assert response.headers["location"] == "/dashboard"


class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_returns_status(self, client):
        with patch("app.main.get_scheduler_status") as mock_status:
            mock_status.return_value = {
                "running": True,
                "jobs": [
                    {"id": "regular_sweep", "name": "Regular Sweep", "next_run": "2024-06-01T00:00:00"},
                    {"id": "mistake_sweep", "name": "Mistake Sweep", "next_run": "2024-06-01T00:00:00"},
                ],
                "job_count": 2,
            }
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["scheduler_running"] is True
            assert data["job_count"] == 2

    @pytest.mark.asyncio
    async def test_health_unhealthy_when_not_running(self, client):
        with patch("app.main.get_scheduler_status") as mock_status:
            mock_status.return_value = {
                "running": False,
                "jobs": [],
                "job_count": 0,
            }
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"
            assert data["scheduler_running"] is False

    @pytest.mark.asyncio
    async def test_health_empty_jobs(self, client):
        with patch("app.main.get_scheduler_status") as mock_status:
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["jobs"] == []
            assert data["job_count"] == 0


class TestConfigEndpoint:

    @pytest.mark.asyncio
    async def test_config_exposes_no_secrets(self, client):
        """Config endpoint must NOT expose API keys or tokens."""
        response = await client.get("/config")
        assert response.status_code == 200
        data = response.json()
        # Should have app and env keys
        assert "app" in data
        assert "env" in data
        # Should NOT include sensitive fields
        json_str = str(data).lower()
        assert "api_key" not in json_str
        assert "secret" not in json_str
        assert "token" not in json_str
        assert "password" not in json_str

    @pytest.mark.asyncio
    async def test_config_has_home_airports(self, client):
        response = await client.get("/config")
        data = response.json()
        assert "home_airports" in data["app"]
        assert "MCI" in data["app"]["home_airports"]

    @pytest.mark.asyncio
    async def test_config_has_deal_thresholds(self, client):
        response = await client.get("/config")
        data = response.json()
        assert "deal_thresholds" in data["app"]
        assert "mistake_fare_percent" in data["app"]["deal_thresholds"]
        assert "flash_sale_percent" in data["app"]["deal_thresholds"]

    @pytest.mark.asyncio
    async def test_config_has_environment(self, client):
        response = await client.get("/config")
        data = response.json()
        assert "env" in data
        assert "amadeus_env" in data["env"]
        assert "log_level" in data["env"]

    @pytest.mark.asyncio
    async def test_config_response_is_stable(self, client):
        """Config response shape must be consistent."""
        r1 = await client.get("/config")
        r2 = await client.get("/config")
        assert r1.json() == r2.json()


class TestDealEndpoints:

    @pytest.mark.asyncio
    async def test_list_deals_empty(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        with patch("app.main.AsyncSessionLocal", return_value=mock_session):
            response = await client.get("/deals")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert data["deals"] == []

    @pytest.mark.asyncio
    async def test_deal_stats_empty(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0
        mock_type_result = MagicMock()
        mock_type_result.all.return_value = []
        mock_route_result = MagicMock()
        mock_route_result.all.return_value = []
        mock_session.execute.side_effect = [mock_count_result, mock_type_result, mock_route_result]
        with patch("app.main.AsyncSessionLocal", return_value=mock_session):
            response = await client.get("/deals/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_deals"] == 0
            assert data["by_type"] == {}
            assert data["top_routes"] == []

    @pytest.mark.asyncio
    async def test_get_deal_not_found(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        with patch("app.main.AsyncSessionLocal", return_value=mock_session):
            response = await client.get("/deals/999")
            assert response.status_code == 404
            data = response.json()
            assert data["detail"] == "Deal not found"

    @pytest.mark.asyncio
    async def test_list_deals_with_data(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_deal = MagicMock()
        mock_deal.id = 1
        mock_deal.route_id = "MCI-LHR-2024-06-01"
        mock_deal.origin = "MCI"
        mock_deal.destination = "LHR"
        mock_deal.departure_date = "2024-06-01"
        mock_deal.airline = "BA"
        mock_deal.flight_numbers = "BA123"
        mock_deal.original_price_usd = 500.0
        mock_deal.current_price_usd = 150.0
        mock_deal.price_drop_percent = 70.0
        mock_deal.deal_type = "mistake_fare"
        mock_deal.booking_url = "https://example.com/book"
        mock_deal.seen_at = None
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_data_scalars = MagicMock()
        mock_data_scalars.all.return_value = [mock_deal]
        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value = mock_data_scalars
        mock_session.execute.side_effect = [mock_count_result, mock_data_result]
        with patch("app.main.AsyncSessionLocal", return_value=mock_session):
            response = await client.get("/deals")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["deals"]) == 1
            assert data["deals"][0]["id"] == 1
            assert data["deals"][0]["origin"] == "MCI"
            assert data["deals"][0]["destination"] == "LHR"

    @pytest.mark.asyncio
    async def test_list_deals_filter_by_type(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_deal = MagicMock()
        mock_deal.id = 1
        mock_deal.route_id = "MCI-LHR-2024-06-01"
        mock_deal.origin = "MCI"
        mock_deal.destination = "LHR"
        mock_deal.departure_date = "2024-06-01"
        mock_deal.airline = "BA"
        mock_deal.flight_numbers = "BA123"
        mock_deal.original_price_usd = 500.0
        mock_deal.current_price_usd = 150.0
        mock_deal.price_drop_percent = 70.0
        mock_deal.deal_type = "mistake_fare"
        mock_deal.booking_url = "https://example.com/book"
        mock_deal.seen_at = None
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_data_scalars = MagicMock()
        mock_data_scalars.all.return_value = [mock_deal]
        mock_data_result = MagicMock()
        mock_data_result.scalars.return_value = mock_data_scalars
        mock_session.execute.side_effect = [mock_count_result, mock_data_result]
        with patch("app.main.AsyncSessionLocal", return_value=mock_session):
            response = await client.get("/deals?deal_type=mistake_fare")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["deals"][0]["deal_type"] == "mistake_fare"

    @pytest.mark.asyncio
    async def test_deal_stats_with_data(self, client):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        mock_type_result = MagicMock()
        mock_type_result.all.return_value = [("mistake_fare", 2), ("flash_sale", 1)]
        mock_route_result = MagicMock()
        mock_route_result.all.return_value = [("MCI", "LHR", 2), ("JFK", "LHR", 1)]
        mock_session.execute.side_effect = [mock_count_result, mock_type_result, mock_route_result]
        with patch("app.main.AsyncSessionLocal", return_value=mock_session):
            response = await client.get("/deals/stats")
            assert response.status_code == 200
            data = response.json()
            assert data["total_deals"] == 3
            assert data["by_type"] == {"mistake_fare": 2, "flash_sale": 1}
            assert len(data["top_routes"]) == 2
            assert data["top_routes"][0]["origin"] == "MCI"
            assert data["top_routes"][0]["destination"] == "LHR"
            assert data["top_routes"][0]["count"] == 2
