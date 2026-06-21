"""Database URL parsing utility for async driver conversion."""

from urllib.parse import urlparse


def get_async_database_url(url: str) -> str:
    """Convert a database URL to its async equivalent.

    sqlite:///path -> sqlite+aiosqlite:///path
    postgresql://user:pass@host/db -> postgresql+asyncpg://user:pass@host/db
    postgres://user:pass@host/db -> postgresql+asyncpg://user:pass@host/db
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        if not url:
            return url
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")
    if parsed.scheme == "sqlite":
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if parsed.scheme in ("postgresql", "postgres"):
        return url.replace(f"{parsed.scheme}://", "postgresql+asyncpg://", 1)
    if parsed.scheme in ("sqlite+aiosqlite", "postgresql+asyncpg"):
        return url
    raise ValueError(f"Unsupported database scheme: {parsed.scheme}")
