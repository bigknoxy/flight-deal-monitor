"""Test dashboard routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Create async test client without lifespan events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_auth():
    """Mock authentication to return a logged-in user."""
    return patch("app.auth.get_current_user", return_value={"user_id": 1})


@pytest.fixture
def mock_db_empty():
    """Mock database session returning empty results."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None

    def execute_side_effect(*args, **kwargs):
        result = MagicMock()
        result.scalar.return_value = 0
        result.scalars.return_value = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


class TestDashboardIndex:

    @pytest.mark.asyncio
    async def test_dashboard_returns_200(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_dashboard_shows_no_routes_empty_state(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [{"id": "sweep", "name": "Sweep", "next_run": "2024-06-01T00:00:00"}],
                "job_count": 1,
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            body = response.text
            assert "Dashboard" in body

    @pytest.mark.asyncio
    async def test_dashboard_scheduler_stopped(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
        ):
            mock_status.return_value = {
                "running": False,
                "jobs": [],
                "job_count": 0,
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Stopped" in response.text

    @pytest.mark.asyncio
    async def test_dashboard_with_deal_stats(self, client, mock_auth):
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None

        call_count = [0]

        async def execute_side(*args, **kw):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # total deals count
                result.scalar.return_value = 5
            elif call_count[0] == 2:
                # by type
                result.all.return_value = [("mistake_fare", 3), ("flash_sale", 2)]
            elif call_count[0] == 3:
                # top routes
                result.all.return_value = [("MCI", "LHR", 3), ("JFK", "LHR", 2)]
            elif call_count[0] == 4:
                # last job
                result.scalar_one_or_none.return_value = None
            else:
                # recent deal for route
                result.scalar_one_or_none.return_value = None
            return result

        session.execute = AsyncMock(side_effect=execute_side)

        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=session),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [{"id": "sweep", "name": "Sweep", "next_run": None}],
                "job_count": 1,
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Total Deals" in response.text


class TestDashboardDeals:

    @pytest.mark.asyncio
    async def test_deals_page_returns_200(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
        ):
            response = await client.get("/dashboard/deals")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_deals_page_empty_state(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
        ):
            response = await client.get("/dashboard/deals")
            assert response.status_code == 200
            assert "No deals detected yet" in response.text

    @pytest.mark.asyncio
    async def test_deals_page_with_data(self, client, mock_auth):
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

        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_session),
        ):
            response = await client.get("/dashboard/deals")
            assert response.status_code == 200
            assert "MCI" in response.text
            assert "LHR" in response.text

    @pytest.mark.asyncio
    async def test_deals_partial_returns_rows(self, client, mock_auth):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        from collections import namedtuple
        DealRow = namedtuple("DealRow", [
            "origin", "destination", "departure_date", "airline",
            "cheapest_price", "original_price", "max_drop", "first_id",
            "booking_url", "seen_at", "deal_type", "flight_numbers", "option_count"
        ])
        mock_row = DealRow(
            origin="MCI", destination="LHR", departure_date="2024-06-01",
            airline="BA", cheapest_price=150.0, original_price=500.0,
            max_drop=70.0, first_id=1, booking_url="https://example.com/book",
            seen_at=None, deal_type="mistake_fare", flight_numbers="BA123",
            option_count=1
        )

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_data_result = MagicMock()
        mock_data_result.all.return_value = [mock_row]
        mock_session.execute.side_effect = [mock_count_result, mock_data_result]

        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_session),
        ):
            response = await client.get("/dashboard/deals/partial?offset=20&limit=20")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]
            assert "MCI" in response.text
            assert "LHR" in response.text

    @pytest.mark.asyncio
    async def test_deals_filter_by_type(self, client, mock_auth):
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        from collections import namedtuple
        DealRow = namedtuple("DealRow", [
            "origin", "destination", "departure_date", "airline",
            "cheapest_price", "original_price", "max_drop", "first_id",
            "booking_url", "seen_at", "deal_type", "flight_numbers", "option_count"
        ])
        mock_row = DealRow(
            origin="JFK", destination="LHR", departure_date="2024-06-01",
            airline="VS", cheapest_price=90.0, original_price=300.0,
            max_drop=70.0, first_id=1, booking_url="https://example.com/book",
            seen_at=None, deal_type="mistake_fare", flight_numbers="VS123",
            option_count=1
        )

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_data_result = MagicMock()
        mock_data_result.all.return_value = [mock_row]
        mock_session.execute.side_effect = [mock_count_result, mock_data_result]

        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_session),
        ):
            response = await client.get("/dashboard/deals?deal_type=mistake_fare")
            assert response.status_code == 200
            assert "mistake_fare" in response.text


class TestDashboardRoutes:

    @pytest.mark.asyncio
    async def test_routes_page_returns_200(self, client, mock_auth):
        with mock_auth:
            response = await client.get("/dashboard/routes")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_routes_page_shows_config(self, client, mock_auth):
        with mock_auth:
            response = await client.get("/dashboard/routes")
            assert response.status_code == 200
            assert "Home Airport" in response.text
            assert "Destinations" in response.text

    @pytest.mark.asyncio
    async def test_routes_add_valid_code(self, client, mock_auth):
        """Test adding a valid airport code."""
        with mock_auth:
            with patch("app.routes.dashboard.os.path.exists") as mock_exists:
                mock_exists.return_value = True
                with patch("app.routes.dashboard.open") as mock_open:
                    mock_file = MagicMock()
                    mock_file.__enter__.return_value = mock_file
                    mock_open.return_value = mock_file

                    # Read should return existing config
                    # Write should succeed
                    mock_file.read.return_value = yaml.dump({
                        "app": {
                            "destinations": ["JFK", "LHR"],
                        }
                    })

                    with patch("app.routes.dashboard.yaml.safe_load") as mock_load:
                        mock_load.return_value = {
                            "app": {
                                "destinations": ["JFK", "LHR"],
                            }
                        }

                        with patch("app.routes.dashboard.yaml.dump") as mock_dump:
                            with patch("app.routes.dashboard._reload_config"):
                                response = await client.post(
                                    "/dashboard/routes/add",
                                    data={"airport_code": "CDG"},
                                )
                                assert response.status_code == 200
                                assert response.headers.get("HX-Redirect") == "/dashboard/routes"

                                mock_dump.assert_called_once()
                                args, _ = mock_dump.call_args
                                assert "CDG" in args[0]["app"]["destinations"]

    @pytest.mark.asyncio
    async def test_routes_add_invalid_code(self, client, mock_auth):
        """Test adding an invalid airport code returns error."""
        with mock_auth:
            response = await client.post(
                "/dashboard/routes/add",
                data={"airport_code": "INVALID"},
            )
            assert response.status_code == 200
            assert "Invalid airport code" in response.text

    @pytest.mark.asyncio
    async def test_routes_add_short_code(self, client, mock_auth):
        """Test adding a too-short code returns error."""
        with mock_auth:
            response = await client.post(
                "/dashboard/routes/add",
                data={"airport_code": "AB"},
            )
            assert response.status_code == 200
            assert "Invalid airport code" in response.text

    @pytest.mark.asyncio
    async def test_routes_add_numeric_code(self, client, mock_auth):
        """Test adding a numeric code returns error."""
        with mock_auth:
            response = await client.post(
                "/dashboard/routes/add",
                data={"airport_code": "123"},
            )
            assert response.status_code == 200
            assert "Invalid airport code" in response.text

    @pytest.mark.asyncio
    async def test_routes_remove_valid_index(self, client, mock_auth):
        """Test removing a destination by valid index."""
        with mock_auth:
            with patch("app.routes.dashboard.os.path.exists") as mock_exists:
                mock_exists.return_value = True
                with patch("app.routes.dashboard.open") as mock_open:
                    mock_file = MagicMock()
                    mock_file.__enter__.return_value = mock_file
                    mock_open.return_value = mock_file

                    with patch("app.routes.dashboard.yaml.safe_load") as mock_load:
                        mock_load.return_value = {
                            "app": {
                                "destinations": ["JFK", "LHR", "CDG"],
                            }
                        }

                        with patch("app.routes.dashboard.yaml.dump") as mock_dump:
                            with patch("app.routes.dashboard._reload_config"):
                                response = await client.post(
                                    "/dashboard/routes/remove",
                                    data={"index": 1},
                                )
                                assert response.status_code == 200
                                assert response.headers.get("HX-Redirect") == "/dashboard/routes"

                                # Verify LHR was removed
                                mock_dump.assert_called_once()
                                args, _ = mock_dump.call_args
                                assert args[0]["app"]["destinations"] == ["JFK", "CDG"]

    @pytest.mark.asyncio
    async def test_routes_remove_invalid_index(self, client, mock_auth):
        """Test removing with invalid index is handled."""
        with mock_auth:
            with patch("app.routes.dashboard.os.path.exists") as mock_exists:
                mock_exists.return_value = True

                with patch("app.routes.dashboard.yaml.safe_load") as mock_load:
                    mock_load.return_value = {
                        "app": {
                            "destinations": ["JFK", "LHR"],
                        }
                    }

                    with patch("app.routes.dashboard.open"):
                        with patch("app.routes.dashboard.yaml.dump"):
                            with patch("app.routes.dashboard._reload_config"):
                                response = await client.post(
                                    "/dashboard/routes/remove",
                                    data={"index": 999},
                                )
                                assert response.status_code == 200
                                assert response.headers.get("HX-Redirect") == "/dashboard/routes"


class TestDashboardHistory:

    @pytest.mark.asyncio
    async def test_history_page_returns_200(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
        ):
            response = await client.get("/dashboard/history")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_history_empty_state(self, client, mock_db_empty, mock_auth):
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
        ):
            response = await client.get("/dashboard/history")
            assert response.status_code == 200
            assert "No sweep history yet" in response.text

    @pytest.mark.asyncio
    async def test_history_with_jobs(self, client, mock_auth):
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None

        mock_job = MagicMock()
        mock_job.job_id = "regular_sweep"
        mock_job.started_at = None
        mock_job.duration_seconds = 12.5
        mock_job.deals_detected = 3
        mock_job.alerts_sent = 2
        mock_job.status = "success"
        mock_job.error_message = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        session.execute = AsyncMock(return_value=mock_result)

        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=session),
        ):
            response = await client.get("/dashboard/history")
            assert response.status_code == 200
            assert "regular_sweep" in response.text
            assert "Success" in response.text

    @pytest.mark.asyncio
    async def test_history_failed_job(self, client, mock_auth):
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None

        mock_job = MagicMock()
        mock_job.job_id = "mistake_sweep"
        mock_job.started_at = None
        mock_job.duration_seconds = 5.0
        mock_job.deals_detected = 0
        mock_job.alerts_sent = 0
        mock_job.status = "failed"
        mock_job.error_message = "API timeout"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        session.execute = AsyncMock(return_value=mock_result)

        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=session),
        ):
            response = await client.get("/dashboard/history")
            assert response.status_code == 200
            assert "Failed" in response.text
            assert "API timeout" in response.text


class TestDashboardSettings:

    @pytest.mark.asyncio
    async def test_settings_page_returns_200(self, client, mock_auth):
        with mock_auth:
            response = await client.get("/dashboard/settings")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_settings_shows_config_sections(self, client, mock_auth):
        with mock_auth:
            response = await client.get("/dashboard/settings")
            assert response.status_code == 200
            assert "Deal Thresholds" in response.text
            assert "Sweep Intervals" in response.text
            assert "Route Multipliers" in response.text
            assert "Cache TTL" in response.text

    @pytest.mark.asyncio
    async def test_settings_shows_config_values(self, client, mock_auth):
        with mock_auth:
            response = await client.get("/dashboard/settings")
            assert response.status_code == 200
            assert "MCI" in response.text
            assert response.text.count("Route Multipliers") >= 1


class TestDashboardNavigation:

    @pytest.mark.asyncio
    async def test_all_pages_have_base_layout(self, client, mock_db_empty, mock_auth):
        """All dashboard pages should include base template elements."""
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            pages = ["/dashboard", "/dashboard/deals", "/dashboard/routes", "/dashboard/history", "/dashboard/settings"]
            for page in pages:
                response = await client.get(page)
                assert response.status_code == 200
                # All pages should include the sidebar nav
                assert "Deal Monitor" in response.text


class TestNotifierWarningBanner:
    """Test notifier warning banner on dashboard."""

    @pytest.mark.asyncio
    async def test_dashboard_shows_warning_when_no_notifiers(self, client, mock_db_empty, mock_auth):
        """Dashboard shows warning banner when no notifiers are configured."""
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
            patch("app.routes.dashboard.config.notifier_status") as mock_notifier,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            mock_notifier.return_value = {
                "telegram": False,
                "email": False,
                "slack": False,
                "discord": False,
                "any_configured": False,
                "partially_configured": [],
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "No alert channels configured" in response.text
            assert "Settings" in response.text

    @pytest.mark.asyncio
    async def test_dashboard_no_warning_when_telegram_configured(self, client, mock_db_empty, mock_auth):
        """Dashboard does NOT show warning when at least one notifier is configured."""
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
            patch("app.routes.dashboard.config.notifier_status") as mock_notifier,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            mock_notifier.return_value = {
                "telegram": True,
                "email": False,
                "slack": False,
                "discord": False,
                "any_configured": True,
                "partially_configured": [],
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "No alert channels configured" not in response.text

    @pytest.mark.asyncio
    async def test_dashboard_shows_partial_config_warning(
        self, client, mock_db_empty, mock_auth
    ):
        """Dashboard shows partially-configured warning when a channel has missing fields."""
        with (
            mock_auth,
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
            patch("app.routes.dashboard.config.notifier_status") as mock_notifier,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            mock_notifier.return_value = {
                "telegram": False,
                "email": False,
                "slack": False,
                "discord": False,
                "any_configured": False,
                "partially_configured": ["telegram"],
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Partially configured alert channels" in response.text
            assert "telegram" in response.text
            assert "No alert channels configured" not in response.text


class TestDetectionHealthBanner:
    """Tests for the detection-health banner on the dashboard index."""

    @pytest.mark.asyncio
    async def test_detection_status_helper_no_success_returns_stale(self):
        """_get_detection_status returns is_stale=True when no successful JobRuns."""
        from app.routes.dashboard import _get_detection_status

        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        # First query (JobRun): no success. Per-route count queries: all 0.
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            ]
            + [
                MagicMock(scalar=MagicMock(return_value=0))
                for _ in range(len(_configured_route_pairs()))
            ]
        )
        with patch(
            "app.routes.dashboard.AsyncSessionLocal", return_value=session
        ):
            result = await _get_detection_status()
        assert result["last_success_at"] is None
        assert result["last_success_age_hours"] is None
        assert result["is_stale"] is True
        assert len(result["routes_with_zero_deals"]) == len(
            _configured_route_pairs()
        )

    @pytest.mark.asyncio
    async def test_detection_status_helper_recent_success_not_stale(self):
        """_get_detection_status returns is_stale=False when scan recent + routes have deals."""
        from datetime import datetime, timedelta

        from app.routes.dashboard import _get_detection_status

        recent = datetime.utcnow() - timedelta(minutes=10)

        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None
        n_routes = len(_configured_route_pairs())
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(
                    scalar_one_or_none=MagicMock(
                        return_value=MagicMock(
                            completed_at=recent, started_at=recent
                        )
                    )
                ),
            ]
            + [MagicMock(scalar=MagicMock(return_value=5)) for _ in range(n_routes)]
        )
        with patch(
            "app.routes.dashboard.AsyncSessionLocal", return_value=session
        ):
            result = await _get_detection_status()
        assert result["last_success_at"] == recent
        assert result["last_success_age_hours"] is not None
        assert result["last_success_age_hours"] < 1.0
        assert result["routes_with_zero_deals"] == []
        assert result["is_stale"] is False

    @pytest.mark.asyncio
    async def test_dashboard_shows_detection_warning_when_stale(
        self, client, mock_db_empty, mock_auth
    ):
        """Dashboard renders banner when detection_status.is_stale=True."""
        stale_status = {
            "last_success_at": None,
            "last_success_age_hours": None,
            "routes_with_zero_deals": ["MCI-JFK"],
            "stale_scan_hours": 6,
            "stale_route_days": 7,
            "is_stale": True,
        }
        with (
            mock_auth,
            patch(
                "app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty
            ),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
            patch(
                "app.routes.dashboard._get_detection_status",
                return_value=stale_status,
            ),
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Detection health needs attention" in response.text
            assert "No successful scans recorded yet" in response.text
            assert "MCI-JFK" in response.text

    @pytest.mark.asyncio
    async def test_dashboard_no_detection_warning_when_healthy(
        self, client, mock_db_empty, mock_auth
    ):
        """Dashboard does NOT render banner when detection_status.is_stale=False."""
        from datetime import datetime, timedelta

        recent = datetime.utcnow() - timedelta(minutes=10)
        healthy_status = {
            "last_success_at": recent,
            "last_success_age_hours": 0.2,
            "routes_with_zero_deals": [],
            "stale_scan_hours": 6,
            "stale_route_days": 7,
            "is_stale": False,
        }
        with (
            mock_auth,
            patch(
                "app.routes.dashboard.AsyncSessionLocal", return_value=mock_db_empty
            ),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
            patch(
                "app.routes.dashboard._get_detection_status",
                return_value=healthy_status,
            ),
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }
            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Detection health needs attention" not in response.text


class TestSendTestAlerts:
    """Tests for the POST /dashboard/settings/test-alerts endpoint."""

    @pytest.mark.asyncio
    async def test_test_alerts_all_ok(self, client, mock_auth):
        """All configured notifiers succeed → per_channel all 'ok', any_ok=True."""
        with (
            mock_auth,
            patch("app.routes.dashboard.config.notifier_status") as mock_status,
            patch("app.alert.telegram_bot.test_connection", new=AsyncMock(return_value=True)),
            patch("app.notifiers.email.email_notifier.test_connection", new=AsyncMock(return_value=True)),
            patch("app.notifiers.slack.slack_notifier.test_connection", new=AsyncMock(return_value=True)),
            patch("app.notifiers.discord.discord_notifier.test_connection", new=AsyncMock(return_value=True)),
        ):
            mock_status.return_value = {
                "telegram": True,
                "email": True,
                "slack": True,
                "discord": True,
                "any_configured": True,
                "partially_configured": [],
            }
            response = await client.post("/dashboard/settings/test-alerts")
            assert response.status_code == 200
            body = response.text
            # Per-channel row labels show each channel name (capitalized) + <strong>OK</strong>.
            assert "Telegram" in body
            assert "Email" in body
            assert "Slack" in body
            assert "Discord" in body
            # 4 notifiers all reported ok
            assert body.count("OK") == 4
            assert "not configured" not in body
            assert "failed" not in body

    @pytest.mark.asyncio
    async def test_test_alerts_unconfigured_channels_show_not_configured(
        self, client, mock_auth
    ):
        """Channels with status[chan]=False render as 'not configured', not 'failed'."""
        with (
            mock_auth,
            patch("app.routes.dashboard.config.notifier_status") as mock_status,
            patch("app.alert.telegram_bot.test_connection", new=AsyncMock(return_value=True)),
            patch("app.notifiers.email.email_notifier.test_connection", new=AsyncMock(return_value=False)),
            patch("app.notifiers.slack.slack_notifier.test_connection", new=AsyncMock(return_value=False)),
            patch("app.notifiers.discord.discord_notifier.test_connection", new=AsyncMock(return_value=False)),
        ):
            mock_status.return_value = {
                "telegram": True,
                "email": False,
                "slack": False,
                "discord": False,
                "any_configured": True,
                "partially_configured": [],
            }
            response = await client.post("/dashboard/settings/test-alerts")
            assert response.status_code == 200
            body = response.text
            # Telegram is configured and ok → shows OK
            assert "OK" in body
            # Other three channels are unconfigured → 'not configured' label
            assert body.count("not configured") == 3

    @pytest.mark.asyncio
    async def test_test_alerts_exception_marks_error(self, client, mock_auth):
        """A notifier throwing an exception renders as 'error', not 'failed'."""
        with (
            mock_auth,
            patch("app.routes.dashboard.config.notifier_status") as mock_status,
            patch("app.alert.telegram_bot.test_connection", new=AsyncMock(side_effect=RuntimeError("boom"))),
            patch("app.notifiers.email.email_notifier.test_connection", new=AsyncMock(return_value=True)),
            patch("app.notifiers.slack.slack_notifier.test_connection", new=AsyncMock(return_value=True)),
            patch("app.notifiers.discord.discord_notifier.test_connection", new=AsyncMock(return_value=True)),
        ):
            mock_status.return_value = {
                "telegram": True,
                "email": True,
                "slack": True,
                "discord": True,
                "any_configured": True,
                "partially_configured": [],
            }
            response = await client.post("/dashboard/settings/test-alerts")
            assert response.status_code == 200
            body = response.text
            assert "error" in body.lower()
            assert "boom" not in body  # don't leak raw exception text to UI


def _configured_route_pairs():
    """Helper returning list of (origin, dest) configured in app config (test-time)."""
    from app.config import config

    return [
        (o, d) for o in config.app.home_airports for d in config.app.destinations
    ]
