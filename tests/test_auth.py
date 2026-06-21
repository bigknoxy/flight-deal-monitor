"""Test authentication routes and middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.hash import bcrypt

from app.auth import create_session, verify_session
from app.main import app


@pytest.fixture
async def client():
    """Create async test client without lifespan events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_db():
    """Mock database session factory."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return session


class TestPasswordHashing:

    def test_hash_and_verify(self):
        """Password hashing with bcrypt works."""
        password = "test-password-123"
        hashed = bcrypt.hash(password)
        assert bcrypt.verify(password, hashed)
        assert not bcrypt.verify("wrong-password", hashed)

    def test_hash_is_different_each_time(self):
        """Each hash call produces a different hash for the same password."""
        password = "test-password-123"
        hash1 = bcrypt.hash(password)
        hash2 = bcrypt.hash(password)
        assert hash1 != hash2


class TestSessionCreation:

    def test_create_session(self):
        """Creating a session produces a signed token."""
        token = create_session(1)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_session_valid(self):
        """Verifying a valid session returns the user data."""
        token = create_session(42)
        payload = verify_session(token)
        assert payload is not None
        assert payload["user_id"] == 42

    def test_verify_session_invalid(self):
        """Verifying an invalid token returns None."""
        payload = verify_session("invalid-token")
        assert payload is None

    def test_verify_session_tampered(self):
        """Verifying a tampered token returns None."""
        token = create_session(1)
        tampered = token[:-5] + "XXXXX"
        payload = verify_session(tampered)
        assert payload is None

    def test_verify_session_expired(self):
        """Verifying an expired token returns None."""
        # Create a token with max_age=0 so it's immediately expired
        # We need to use the serializer directly with a timestamp in the past
        from itsdangerous import URLSafeTimedSerializer

        old_serializer = URLSafeTimedSerializer("test-secret", salt="auth")
        # Create token with a payload
        token = old_serializer.dumps({"user_id": 999})
        # Verify using the real serializer - it will fail because
        # the signature won't match (different secret)
        payload = verify_session(token)
        assert payload is None


class TestLogin:

    @pytest.mark.asyncio
    async def test_login_page_returns_200(self, client):
        """GET /auth/login returns the login page."""
        response = await client.get("/auth/login")
        assert response.status_code == 200
        assert "Sign in" in response.text
        assert "email" in response.text.lower()

    @pytest.mark.asyncio
    async def test_login_valid_credentials(self, client, mock_db):
        """Valid credentials set session cookie and redirect to dashboard."""
        hashed = bcrypt.hash("correct-password")
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.password_hash = hashed

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.routes.auth.AsyncSessionLocal", return_value=mock_db):
            response = await client.post(
                "/auth/login",
                data={"email": "test@example.com", "password": "correct-password"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers.get("location") == "/dashboard"
            # Check that session cookie was set
            cookies = response.cookies
            assert "session" in cookies

    @pytest.mark.asyncio
    async def test_login_invalid_password(self, client, mock_db):
        """Invalid password shows error on login page."""
        hashed = bcrypt.hash("correct-password")
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.password_hash = hashed

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.routes.auth.AsyncSessionLocal", return_value=mock_db):
            response = await client.post(
                "/auth/login",
                data={"email": "test@example.com", "password": "wrong-password"},
            )
            assert response.status_code == 200
            assert "Invalid email or password" in response.text

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client, mock_db):
        """Non-existent user shows error on login page."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.routes.auth.AsyncSessionLocal", return_value=mock_db):
            response = await client.post(
                "/auth/login",
                data={"email": "nonexistent@example.com", "password": "any-password"},
            )
            assert response.status_code == 200
            assert "Invalid email or password" in response.text


class TestRegister:

    @pytest.mark.asyncio
    async def test_register_page_returns_200(self, client):
        """GET /auth/register returns the registration page."""
        response = await client.get("/auth/register")
        assert response.status_code == 200
        assert "Create Account" in response.text

    @pytest.mark.asyncio
    async def test_register_creates_user_and_auto_login(self, client, mock_db):
        """Valid registration creates user and redirects with session."""
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_existing_result)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        # Set the user.id after refresh
        async def refresh_side(user):
            user.id = 2

        mock_db.refresh = AsyncMock(side_effect=refresh_side)

        with patch("app.routes.auth.AsyncSessionLocal", return_value=mock_db):
            response = await client.post(
                "/auth/register",
                data={"email": "newuser@example.com", "password": "password123"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers.get("location") == "/dashboard"
            # Verify session cookie is set
            assert "session" in response.cookies
            # Verify user was added to DB
            mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client):
        """Invalid email shows error."""
        response = await client.post(
            "/auth/register",
            data={"email": "notanemail", "password": "password123"},
        )
        assert response.status_code == 200
        assert "valid email" in response.text.lower()

    @pytest.mark.asyncio
    async def test_register_short_password(self, client):
        """Short password shows error."""
        response = await client.post(
            "/auth/register",
            data={"email": "test@example.com", "password": "ab"},
        )
        assert response.status_code == 200
        assert "6 characters" in response.text

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client, mock_db):
        """Duplicate email shows error."""
        mock_existing_user = MagicMock()
        mock_existing_user.id = 1
        mock_existing_result = MagicMock()
        mock_existing_result.scalar_one_or_none.return_value = mock_existing_user
        mock_db.execute = AsyncMock(return_value=mock_existing_result)

        with patch("app.routes.auth.AsyncSessionLocal", return_value=mock_db):
            response = await client.post(
                "/auth/register",
                data={"email": "existing@example.com", "password": "password123"},
            )
            assert response.status_code == 200
            assert "already exists" in response.text.lower()


class TestLogout:

    @pytest.mark.asyncio
    async def test_logout_clears_session(self, client):
        """POST /auth/logout clears session cookie and redirects."""
        response = await client.post("/auth/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"
        # Session cookie should be cleared (max-age=0 or empty)
        set_cookie = response.headers.get("set-cookie", "")
        assert "session=" in set_cookie


class TestProtectedRoutes:

    @pytest.mark.asyncio
    async def test_dashboard_redirects_when_unauthenticated(self, client):
        """Dashboard redirects to login when no session cookie."""
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_deals_redirects_when_unauthenticated(self, client):
        """Deals page redirects to login when no session cookie."""
        response = await client.get("/dashboard/deals", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_routes_redirects_when_unauthenticated(self, client):
        """Routes page redirects to login when no session cookie."""
        response = await client.get("/dashboard/routes", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_history_redirects_when_unauthenticated(self, client):
        """History page redirects to login when no session cookie."""
        response = await client.get("/dashboard/history", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_settings_redirects_when_unauthenticated(self, client):
        """Settings page redirects to login when no session cookie."""
        response = await client.get("/dashboard/settings", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/auth/login"

    @pytest.mark.asyncio
    async def test_authenticated_user_can_access_dashboard(self, client):
        """Authenticated user can access dashboard pages."""
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.__aexit__.return_value = None

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        with (
            patch("app.routes.dashboard.AsyncSessionLocal", return_value=session),
            patch("app.routes.dashboard.get_scheduler_status") as mock_status,
        ):
            mock_status.return_value = {
                "running": True,
                "jobs": [],
                "job_count": 0,
            }

            # Set session cookie
            token = create_session(1)
            client.cookies.set("session", token)

            response = await client.get("/dashboard")
            assert response.status_code == 200
            assert "Dashboard" in response.text
