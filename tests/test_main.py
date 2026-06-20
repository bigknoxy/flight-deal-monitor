"""Test FastAPI application endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    """Create async test client without lifespan events (to avoid DB init)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRootEndpoint:

    @pytest.mark.asyncio
    async def test_root_returns_app_info(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "flight-deal-monitor"
        assert data["version"] == "1.0.0"
        assert "description" in data

    @pytest.mark.asyncio
    async def test_root_content_type(self, client):
        response = await client.get("/")
        assert response.headers["content-type"] == "application/json"


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
