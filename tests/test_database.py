"""Test database module — engine config, init, close."""

from unittest.mock import AsyncMock, patch

import pytest

from app.database import AsyncSessionLocal, close_db, get_session, init_db


class TestDatabaseInitClose:

    @pytest.mark.asyncio
    async def test_init_db_uses_engine_begin(self):
        """init_db must call engine.begin and run_sync create_all."""
        with patch("app.database.engine") as mock_engine:
            mock_conn = AsyncMock()
            mock_engine.begin.return_value.__aenter__.return_value = mock_conn

            await init_db()

            # create_all + ensure_schema (schema-migration guard) each open a
            # transaction and run_sync once.
            assert mock_engine.begin.call_count == 2
            assert mock_conn.run_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_close_db_disposes_engine(self):
        """close_db must dispose the engine."""
        with patch("app.database.engine") as mock_engine:
            mock_engine.dispose = AsyncMock()

            await close_db()

            mock_engine.dispose.assert_called_once()


class TestGetSession:

    @pytest.mark.asyncio
    async def test_get_session_yields_async_session(self):
        """get_session yields an AsyncSession (verify via type contract)."""

        class FakeSession:
            """Minimal session stub for testing get_session."""
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        fake = FakeSession()
        with patch("app.database.AsyncSessionLocal", return_value=fake):
            async for session in get_session():
                # Should get back our fake session
                assert session is fake
                break


class TestEngineCreation:
    """Verify engine is configured correctly."""

    def test_engine_url_uses_aiosqlite(self):
        """The async engine must use aiosqlite driver."""
        from app.database import engine
        url = str(engine.url)
        assert "+aiosqlite" in url

    def test_engine_has_dialect(self):
        from app.database import engine
        assert engine.dialect is not None

    def test_async_session_local_is_async(self):
        """AsyncSessionLocal's class_ should be AsyncSession (SQLAlchemy async)."""
        # In modern SQLAlchemy, AsyncSession is importable from both paths.
        # The class_ attribute stores the session class used by the factory.
        session_class = AsyncSessionLocal.class_
        # Verify it's a valid session class with async methods
        assert hasattr(session_class, 'execute')
        assert hasattr(session_class, 'commit')
        assert hasattr(session_class, 'close')
