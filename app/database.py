"""Database setup and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import config
from app.utils.database_url import get_async_database_url

# Create async engine
database_url = get_async_database_url(config.env.database_url)
engine_kwargs: dict = {"echo": config.env.log_level == "DEBUG"}
if config.env.database_url.startswith(("postgresql://", "postgres://")):
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(database_url, **engine_kwargs)

# Create async session factory
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
