"""Test alert history API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_session


@pytest.fixture
def mock_flight_deal_1():
    """Create a mock FlightDeal."""
    from app.models.flight import FlightDeal

    return FlightDeal(
        id=1,
        route_id="route_abc123",
        origin="MCI",
        destination="LHR",
        departure_date="2024-06-15",
        airline="British Airways",
        flight_numbers="BA123",
        original_price_usd=500.0,
        current_price_usd=300.0,
        price_drop_percent=40.0,
        deal_type="flash_sale",
        booking_url="https://example.com/book1",
        seen_at=datetime.now(UTC),
        expired_at=None,
    )


@pytest.fixture
def mock_flight_deal_2():
    """Create a mock FlightDeal."""
    from app.models.flight import FlightDeal

    return FlightDeal(
        id=2,
        route_id="route_def456",
        origin="LAX",
        destination="NRT",
        departure_date="2024-07-01",
        airline="ANA",
        flight_numbers="NH123",
        original_price_usd=800.0,
        current_price_usd=200.0,
        price_drop_percent=75.0,
        deal_type="mistake_fare",
        booking_url="https://example.com/book2",
        seen_at=datetime.now(UTC),
        expired_at=None,
    )


@pytest.fixture
def mock_alert_1(mock_flight_deal_1):
    """Create a mock AlertHistory."""
    from app.models.flight import AlertHistory

    return AlertHistory(
        id=1,
        flight_deal_id=1,
        sent_at=datetime.now(UTC),
        telegram_message_id="12345",
        status="sent",
        error_message=None,
    )


@pytest.fixture
def mock_alert_2(mock_flight_deal_2):
    """Create a mock AlertHistory."""
    from app.models.flight import AlertHistory

    return AlertHistory(
        id=2,
        flight_deal_id=2,
        sent_at=datetime.now(UTC) - timedelta(hours=2),
        telegram_message_id="67890",
        status="sent",
        error_message=None,
    )


@pytest.fixture
def mock_alert_3(mock_flight_deal_2):
    """Create a mock AlertHistory with failed status."""
    from app.models.flight import AlertHistory

    return AlertHistory(
        id=3,
        flight_deal_id=2,
        sent_at=datetime.now(UTC) - timedelta(hours=5),
        telegram_message_id=None,
        status="failed",
        error_message="Telegram API error",
    )


def create_mock_session(alert_deal_pairs, total_count=None):
    """Create a mock async database session that returns given pairs.

    The session.execute() is async and returns a MagicMock result.
    The result.all() returns the pairs (for main queries).
    The result.scalar_one() returns the count (for count queries).
    """
    if total_count is None:
        total_count = len(alert_deal_pairs)

    session = AsyncMock()

    def execute_side_effect(query):
        result = MagicMock()
        query_str = str(query).lower()

        if "count" in query_str:
            result.scalar_one.return_value = total_count
        else:
            result.all.return_value = alert_deal_pairs
        return result

    session.execute.side_effect = execute_side_effect
    return session


def create_detail_session(alert_deal_pair):
    """Create a mock session that returns a single alert-deal pair for detail queries."""
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = alert_deal_pair
    session.execute.return_value = result
    return session


def create_not_found_session():
    """Create a mock session that returns None (for 404 tests)."""
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None
    session.execute.return_value = result
    return session


@pytest.fixture
def test_client_with_history(mock_alert_1, mock_alert_2, mock_alert_3,
                              mock_flight_deal_1, mock_flight_deal_2):
    """Create a test client with mocked database session returning alert history."""
    pairs = [
        (mock_alert_1, mock_flight_deal_1),
        (mock_alert_2, mock_flight_deal_2),
        (mock_alert_3, mock_flight_deal_2),
    ]
    mock_session = create_mock_session(pairs, total_count=3)

    async def override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


class TestAlertHistoryList:
    """Tests for GET /alerts/history endpoint."""

    def test_get_alert_history_default(self, test_client_with_history):
        """Test getting alert history with default parameters."""
        response = test_client_with_history.get("/alerts/history")
        assert response.status_code == 200

        data = response.json()
        assert "alerts" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 3
        assert len(data["alerts"]) == 3

    def test_alert_history_response_structure(self, test_client_with_history):
        """Test that alert history response has correct structure."""
        response = test_client_with_history.get("/alerts/history")
        assert response.status_code == 200

        data = response.json()
        alert = data["alerts"][0]

        # Check alert fields
        assert "id" in alert
        assert "flight_deal_id" in alert
        assert "sent_at" in alert
        assert "telegram_message_id" in alert
        assert "status" in alert
        assert "error_message" in alert

        # Check nested flight_deal fields
        assert "flight_deal" in alert
        deal = alert["flight_deal"]
        assert "id" in deal
        assert "route_id" in deal
        assert "origin" in deal
        assert "destination" in deal
        assert "departure_date" in deal
        assert "airline" in deal
        assert "flight_numbers" in deal
        assert "original_price_usd" in deal
        assert "current_price_usd" in deal
        assert "price_drop_percent" in deal
        assert "deal_type" in deal
        assert "booking_url" in deal
        assert "seen_at" in deal

    def test_get_alert_history_with_limit(self, test_client_with_history):
        """Test getting alert history with custom limit."""
        response = test_client_with_history.get("/alerts/history?limit=10")
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 10

    def test_get_alert_history_with_offset(self, test_client_with_history):
        """Test getting alert history with offset."""
        response = test_client_with_history.get("/alerts/history?offset=5")
        assert response.status_code == 200

        data = response.json()
        assert data["offset"] == 5

    def test_get_alert_history_limit_max(self, test_client_with_history):
        """Test that limit above 200 is rejected by validation."""
        response = test_client_with_history.get("/alerts/history?limit=500")
        assert response.status_code == 422

    def test_get_alert_history_limit_at_max(self, test_client_with_history):
        """Test that limit at 200 is accepted."""
        response = test_client_with_history.get("/alerts/history?limit=200")
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 200

    def test_get_alert_history_limit_min(self, test_client_with_history):
        """Test that limit minimum is 1."""
        response = test_client_with_history.get("/alerts/history?limit=0")
        assert response.status_code == 422

    def test_get_alert_history_with_start_date(self, test_client_with_history):
        """Test filtering by start_date."""
        response = test_client_with_history.get("/alerts/history?start_date=2024-01-01")
        assert response.status_code == 200

    def test_get_alert_history_with_end_date(self, test_client_with_history):
        """Test filtering by end_date."""
        response = test_client_with_history.get("/alerts/history?end_date=2024-12-31")
        assert response.status_code == 200

    def test_get_alert_history_with_date_range(self, test_client_with_history):
        """Test filtering by date range."""
        response = test_client_with_history.get(
            "/alerts/history?start_date=2024-01-01&end_date=2024-12-31"
        )
        assert response.status_code == 200

    def test_get_alert_history_with_flash_sale_deal_type(self, test_client_with_history):
        """Test filtering by deal_type=flash_sale."""
        response = test_client_with_history.get("/alerts/history?deal_type=flash_sale")
        assert response.status_code == 200

    def test_get_alert_history_with_mistake_fare_deal_type(self, test_client_with_history):
        """Test filtering by deal_type=mistake_fare."""
        response = test_client_with_history.get("/alerts/history?deal_type=mistake_fare")
        assert response.status_code == 200

    def test_get_alert_history_invalid_deal_type(self, test_client_with_history):
        """Test that invalid deal_type returns 400."""
        response = test_client_with_history.get("/alerts/history?deal_type=invalid_type")
        assert response.status_code == 400
        assert "Invalid deal_type" in response.json()["detail"]

    def test_get_alert_history_invalid_start_date(self, test_client_with_history):
        """Test that invalid start_date format returns 400."""
        response = test_client_with_history.get("/alerts/history?start_date=invalid-date")
        assert response.status_code == 400
        assert "Invalid start_date format" in response.json()["detail"]

    def test_get_alert_history_invalid_end_date(self, test_client_with_history):
        """Test that invalid end_date format returns 400."""
        response = test_client_with_history.get("/alerts/history?end_date=invalid-date")
        assert response.status_code == 400
        assert "Invalid end_date format" in response.json()["detail"]

    def test_get_alert_history_all_filters(self, test_client_with_history):
        """Test with all filters combined."""
        response = test_client_with_history.get(
            "/alerts/history?start_date=2024-01-01&end_date=2024-12-31"
            "&deal_type=flash_sale&limit=10&offset=0"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_alert_history_includes_flight_deal_data(self, test_client_with_history):
        """Test that alert history includes nested flight deal data."""
        response = test_client_with_history.get("/alerts/history")
        assert response.status_code == 200

        data = response.json()
        for alert in data["alerts"]:
            assert alert["flight_deal"] is not None
            assert alert["flight_deal"]["id"] == alert["flight_deal_id"]

    def test_alert_history_failed_alert_has_error(self, test_client_with_history):
        """Test that failed alerts include error message."""
        response = test_client_with_history.get("/alerts/history")
        assert response.status_code == 200

        data = response.json()
        failed_alerts = [a for a in data["alerts"] if a["status"] == "failed"]
        assert len(failed_alerts) > 0
        assert failed_alerts[0]["error_message"] is not None
        assert failed_alerts[0]["telegram_message_id"] is None


class TestGetAlert:
    """Tests for GET /alerts/{alert_id} endpoint."""

    def test_get_alert_found(self, mock_alert_1, mock_flight_deal_1):
        """Test getting a specific alert by ID."""
        session = create_detail_session((mock_alert_1, mock_flight_deal_1))

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session

        with TestClient(app) as client:
            response = client.get("/alerts/1")
            assert response.status_code == 200

            data = response.json()
            assert data["id"] == 1
            assert data["flight_deal_id"] == 1
            assert data["status"] == "sent"
            assert data["telegram_message_id"] == "12345"

            # Check nested flight_deal
            assert data["flight_deal"] is not None
            assert data["flight_deal"]["id"] == 1
            assert data["flight_deal"]["origin"] == "MCI"
            assert data["flight_deal"]["destination"] == "LHR"
            assert data["flight_deal"]["deal_type"] == "flash_sale"

        app.dependency_overrides.clear()

    def test_get_alert_not_found(self):
        """Test getting a non-existent alert returns 404."""
        session = create_not_found_session()

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session

        with TestClient(app) as client:
            response = client.get("/alerts/999")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_get_alert_failed_status(self, mock_alert_3, mock_flight_deal_2):
        """Test getting an alert with failed status."""
        session = create_detail_session((mock_alert_3, mock_flight_deal_2))

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session

        with TestClient(app) as client:
            response = client.get("/alerts/3")
            assert response.status_code == 200

            data = response.json()
            assert data["id"] == 3
            assert data["status"] == "failed"
            assert data["error_message"] == "Telegram API error"
            assert data["telegram_message_id"] is None

        app.dependency_overrides.clear()

    def test_get_alert_mistake_fare(self, mock_alert_2, mock_flight_deal_2):
        """Test getting an alert for a mistake fare deal."""
        session = create_detail_session((mock_alert_2, mock_flight_deal_2))

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session

        with TestClient(app) as client:
            response = client.get("/alerts/2")
            assert response.status_code == 200

            data = response.json()
            assert data["id"] == 2
            assert data["flight_deal"]["deal_type"] == "mistake_fare"
            assert data["flight_deal"]["origin"] == "LAX"
            assert data["flight_deal"]["destination"] == "NRT"

        app.dependency_overrides.clear()


class TestAlertHistoryIntegration:
    """Integration tests for alert history endpoints."""

    def test_history_and_detail_consistency(self, mock_alert_1, mock_flight_deal_1,
                                             mock_alert_2, mock_flight_deal_2,
                                             mock_alert_3):
        """Test that history list and detail endpoint return consistent data."""
        pairs = [
            (mock_alert_1, mock_flight_deal_1),
            (mock_alert_2, mock_flight_deal_2),
            (mock_alert_3, mock_flight_deal_2),
        ]

        # First: test history list
        list_session = create_mock_session(pairs, total_count=3)

        async def override_list_session():
            yield list_session

        app.dependency_overrides[get_session] = override_list_session

        with TestClient(app) as client:
            response = client.get("/alerts/history")
            assert response.status_code == 200
            history_data = response.json()

        # Second: test detail endpoint for the first alert
        detail_session = create_detail_session((mock_alert_1, mock_flight_deal_1))

        async def override_detail_session():
            yield detail_session

        app.dependency_overrides[get_session] = override_detail_session

        with TestClient(app) as client:
            detail_response = client.get(f"/alerts/{history_data['alerts'][0]['id']}")
            assert detail_response.status_code == 200
            detail_data = detail_response.json()

        app.dependency_overrides.clear()

        # Verify consistency
        assert detail_data["id"] == history_data["alerts"][0]["id"]
        assert detail_data["flight_deal_id"] == history_data["alerts"][0]["flight_deal_id"]
        assert detail_data["status"] == history_data["alerts"][0]["status"]
        assert (
            detail_data["telegram_message_id"]
            == history_data["alerts"][0]["telegram_message_id"]
        )

    def test_history_pagination_metadata(self, test_client_with_history):
        """Test that pagination metadata is correct."""
        response = test_client_with_history.get("/alerts/history?limit=10&offset=0")
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert data["total"] >= 0
        assert isinstance(data["alerts"], list)

    def test_root_endpoint(self, test_client_with_history):
        """Test root endpoint still works."""
        response = test_client_with_history.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data

    def test_health_endpoint(self, test_client_with_history):
        """Test health endpoint still works."""
        response = test_client_with_history.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "scheduler_running" in data
