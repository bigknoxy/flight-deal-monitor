"""Database setup and session management."""

import os
from collections.abc import AsyncGenerator
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import config
from app.models.flight import FlightDeal, PriceObservation
from app.models.telegram import TelegramSubscription
from app.utils.database_url import get_async_database_url

# Ensure the SQLite database directory exists so a volume-mounted path
# (e.g. docker-compose ./data:/app/data with sqlite:///./data/flight_deals.db)
# never fails to create on first run.
_async_url = get_async_database_url(config.env.database_url)
if _async_url.startswith("sqlite"):
    _parsed = urlparse(_async_url)
    _db_path = _parsed.path.lstrip("/")
    _db_dir = os.path.dirname(_db_path)
    if _db_dir and not os.path.exists(_db_dir):
        os.makedirs(_db_dir, exist_ok=True)

# Create async engine
database_url = _async_url
engine_kwargs: dict = {"echo": config.env.log_level == "DEBUG"}
if config.env.database_url.startswith(("postgresql://", "postgres://")):
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(database_url, **engine_kwargs)

if database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

# Create async session factory
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def ensure_schema() -> None:
    """Add any missing columns to existing tables (prod migration guard).

    ``SQLModel.metadata.create_all`` only creates tables that do not yet exist;
    it never adds columns to a table that already exists. For a prod DB that
    predates a schema change (e.g. the Tier-2 ``FlightDeal`` columns), this
    brings the schema up to date on startup so the app boots without a manual
    Alembic migration.

    New columns are added as nullable (with a DEFAULT for non-nullable columns
    that carry a Python default), which is safe on both SQLite and Postgres.
    """

    def _default_clause(col) -> str:
        default = col.default
        arg = getattr(default, "arg", None)
        if arg is None:
            return ""
        if isinstance(arg, bool):
            return " DEFAULT TRUE" if arg else " DEFAULT FALSE"
        if isinstance(arg, str):
            escaped = arg.replace("'", "''")
            return f" DEFAULT '{escaped}'"
        if isinstance(arg, int | float):
            return f" DEFAULT {arg}"
        return ""

    def _sync(conn) -> None:
        inspector = sa_inspect(conn)
        for model in (FlightDeal, PriceObservation, TelegramSubscription):
            table = model.__tablename__
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for col in model.__table__.columns:
                if col.name in existing:
                    continue
                col_type = col.type.compile(dialect=conn.dialect)
                ddl = (
                    f"ALTER TABLE {table} ADD COLUMN {col.name} {col_type}"
                    f"{_default_clause(col)}"
                )
                conn.exec_driver_sql(ddl)

    async with engine.begin() as conn:
        await conn.run_sync(_sync)


async def init_db() -> None:
    """Initialize database tables and migrate any missing columns."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    await ensure_schema()


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
