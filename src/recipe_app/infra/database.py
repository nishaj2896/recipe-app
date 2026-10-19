"""The async engine; one per process, opened and closed by its owner."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def create_engine(url: str) -> AsyncEngine:
    """An engine whose pool checks a connection before handing it out.

    Pool sizes and timeouts are SQLAlchemy's defaults until Task 4 tunes them.
    """
    return create_async_engine(url, pool_pre_ping=True)
