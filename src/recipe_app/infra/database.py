"""The async engine, its time budgets, and what counts as the database being
unavailable (ADR-0013 rules 1, 2, 3 and 6). One engine per process, opened and
closed by its owner.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from recipe_app.services.ports import StoreUnavailableError

logger = logging.getLogger(__name__)

# SQLSTATE classes that mean "not now", not "your query is wrong": 08 is a
# lost or refused connection, 57 an operator or the server stopping the query
# (57014 is our statement_timeout), 53 the server out of connections, memory or
# disk.
_UNAVAILABLE_SQLSTATE_CLASSES = ("08", "57", "53")


@dataclass(frozen=True, slots=True)
class EngineLimits:
    """The API's budgets (ADR-0013 rules 2 and 6); `db sync` runs without them."""

    connect_timeout: float = 3
    pool_timeout: float = 2
    statement_timeout: float = 3
    pool_size: int = 5
    max_overflow: int = 5

    @property
    def client_timeout(self) -> float:
        """asyncpg's own limit, a second past the server's: it frees us when a
        dead network never delivers the server's cancel."""
        return self.statement_timeout + 1


def create_engine(url: str, limits: EngineLimits | None = None) -> AsyncEngine:
    """An engine whose pool checks a connection before handing it out.

    Every transaction starts by setting jit off (issue #34: compiling the broad
    search cost up to 700 ms) and, with limits, the statement timeout. Both are
    transaction-local, so they hold behind any connection pooler (issue #37);
    a startup parameter would be refused by PgBouncer.
    """
    options: dict[str, Any] = {}
    connect_args: dict[str, Any] = {}
    settings = {"jit": "off"}
    if limits is not None:
        options = {
            "pool_size": limits.pool_size,
            "max_overflow": limits.max_overflow,
            "pool_timeout": limits.pool_timeout,
        }
        connect_args = {
            "timeout": limits.connect_timeout,
            "command_timeout": limits.client_timeout,
        }
        settings["statement_timeout"] = f"{round(limits.statement_timeout * 1000)}ms"

    engine = create_async_engine(
        url, pool_pre_ping=True, connect_args=connect_args, **options
    )
    _apply_on_begin(engine, settings)
    return engine


def _apply_on_begin(engine: AsyncEngine, settings: dict[str, str]) -> None:
    # One statement: asyncpg prepares what SQLAlchemy sends, and a prepared
    # statement can't hold two commands. set_config(..., true) is SET LOCAL.
    calls = ", ".join(
        f"set_config('{name}', '{value}', true)" for name, value in settings.items()
    )
    statement = f"SELECT {calls}"

    @event.listens_for(engine.sync_engine, "begin")
    def set_local(connection: Connection) -> None:
        connection.exec_driver_sql(statement)


def unavailable_cause(error: BaseException) -> str | None:
    """Why the database can't answer now, or None if `error` is something else.

    The cause names a kind and a class, never the error's text, which can hold
    a host name or part of the SQL.
    """
    if isinstance(error, PoolTimeoutError):
        return "pool timeout"
    if isinstance(error, DBAPIError):
        sqlstate = _sqlstate(error)
        if sqlstate == "57014":
            # 57014 is any cancel: our statement_timeout, or someone running
            # pg_cancel_backend. The server's own message tells them apart; it
            # is read, never logged. A server whose messages aren't in English
            # gets the honest, vaguer label.
            if "statement timeout" in str(error.orig):
                return "statement timeout"
            return "query cancelled (57014)"
        if error.connection_invalidated:
            return f"connection lost ({sqlstate or _name(error)})"
        if sqlstate is not None and sqlstate.startswith(_UNAVAILABLE_SQLSTATE_CLASSES):
            return f"database refused ({sqlstate})"
        if _is_timeout(error.orig) or _is_timeout(error.__cause__):
            return "statement timeout (client)"
        if isinstance(error.orig, OSError) or isinstance(error.__cause__, OSError):
            return f"connection failed ({_name(error)})"
        return None
    if isinstance(error, TimeoutError | asyncio.TimeoutError):
        return "connect timeout"
    if isinstance(error, OSError):
        return f"connection failed ({type(error).__name__})"
    return None


@asynccontextmanager
async def unavailable_as_store_error() -> AsyncIterator[None]:
    """Turns the database being unavailable into StoreUnavailableError.

    Used around every query an API request makes, so only this boundary maps
    timeouts and socket errors to a 503 (ADR-0013 rule 1); the same error
    raised anywhere else stays a 500.
    """
    try:
        yield
    except Exception as error:
        cause = unavailable_cause(error)
        if cause is None:
            raise
        raise StoreUnavailableError(cause) from error


def _sqlstate(error: DBAPIError) -> str | None:
    for candidate in (
        error.orig,
        error.__cause__,
        getattr(error.orig, "__cause__", None),
    ):
        sqlstate = getattr(candidate, "sqlstate", None)
        if isinstance(sqlstate, str):
            return sqlstate
    return None


def _is_timeout(error: object) -> bool:
    return isinstance(error, TimeoutError | asyncio.TimeoutError)


def _name(error: DBAPIError) -> str:
    original = error.__cause__ or error.orig
    return type(original).__name__
