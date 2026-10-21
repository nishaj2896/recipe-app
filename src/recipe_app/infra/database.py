"""The async engine; one per process, opened and closed by its owner."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# JIT compiles a query to machine code when its estimated cost is high. The
# search's broad queries cross that line, and compiling then takes longer
# than running: up to 700 ms on 50,000 recipes (issue #34).
SERVER_SETTINGS = {"jit": "off"}


def create_engine(url: str) -> AsyncEngine:
    """An engine whose pool checks a connection before handing it out.

    Pool sizes and timeouts are SQLAlchemy's defaults until Task 4 tunes them.
    """
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"server_settings": SERVER_SETTINGS},
    )
