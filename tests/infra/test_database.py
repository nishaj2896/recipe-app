"""The engine's budgets and what counts as the database being unavailable
(ADR-0013 rules 1, 2, 3 and 6)."""

import asyncio
import socket
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.infra.database import (
    EngineLimits,
    create_engine,
    unavailable_as_store_error,
    unavailable_cause,
)
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.services.ports import StoreUnavailableError

pytestmark = pytest.mark.anyio

SOME_RECIPE = UUID("01938e5c-0000-7000-8000-000000000000")


class DriverError(Exception):
    """What a driver error looks like to SQLAlchemy: it may carry a SQLSTATE."""

    def __init__(
        self, sqlstate: str | None = None, message: str = "password=hunter2"
    ) -> None:
        super().__init__(f"{message} at db.internal")
        self.sqlstate = sqlstate


def wrapped(
    sqlstate: str | None = None,
    *,
    invalidated: bool = False,
    message: str = "password=hunter2",
) -> DBAPIError:
    return DBAPIError(
        "SELECT secret",
        {},
        DriverError(sqlstate, message),
        connection_invalidated=invalidated,
    )


TIMED_OUT = "canceling statement due to statement timeout"
CANCELLED = "canceling statement due to user request"


# Which errors mean "not now"


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        pytest.param(PoolTimeoutError(), "pool timeout", id="pool"),
        pytest.param(
            wrapped("57014", message=TIMED_OUT), "statement timeout", id="statement"
        ),
        pytest.param(
            wrapped("57014", message=CANCELLED),
            "query cancelled (57014)",
            id="cancelled",
        ),
        pytest.param(
            wrapped("57P01", invalidated=True), "connection lost (57P01)", id="killed"
        ),
        pytest.param(
            wrapped(invalidated=True), "connection lost (DriverError)", id="dropped"
        ),
        pytest.param(wrapped("08006"), "database refused (08006)", id="link"),
        pytest.param(wrapped("53300"), "database refused (53300)", id="too-many"),
        pytest.param(TimeoutError(), "connect timeout", id="connect-timeout"),
        pytest.param(
            ConnectionRefusedError(),
            "connection failed (ConnectionRefusedError)",
            id="refused",
        ),
    ],
)
def test_unavailable_causes(error: BaseException, cause: str) -> None:
    assert unavailable_cause(error) == cause


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(wrapped("42P01"), id="undefined-table"),
        pytest.param(wrapped("23505"), id="unique-violation"),
        pytest.param(wrapped(None), id="no-sqlstate"),
        pytest.param(ValueError("bug"), id="bug"),
        pytest.param(KeyError("bug"), id="key-error"),
    ],
)
def test_bugs_are_not_unavailability(error: BaseException) -> None:
    """A broken query is our bug: it stays a 500, never a quiet 503."""
    assert unavailable_cause(error) is None


def test_the_cause_never_holds_the_error_text() -> None:
    for error in (wrapped("57014"), wrapped("08006"), wrapped(invalidated=True)):
        cause = unavailable_cause(error) or ""
        assert "hunter2" not in cause
        assert "SELECT" not in cause


async def test_the_boundary_raises_store_unavailable() -> None:
    with pytest.raises(StoreUnavailableError) as caught:
        async with unavailable_as_store_error():
            raise PoolTimeoutError()

    assert caught.value.cause == "pool timeout"
    assert isinstance(caught.value.__cause__, PoolTimeoutError)


async def test_the_boundary_lets_bugs_through() -> None:
    with pytest.raises(ValueError, match="bug"):
        async with unavailable_as_store_error():
            raise ValueError("bug")


# The engine against a real database


async def settings_of(engine: AsyncEngine) -> tuple[str, str]:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT current_setting('jit'), "
                    "current_setting('statement_timeout')"
                )
            )
        ).one()
    return row[0], row[1]


async def test_every_transaction_turns_jit_off_and_sets_the_budget(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url, EngineLimits(statement_timeout=3))
    try:
        # Twice: the second transaction reuses the pooled connection, and
        # SET LOCAL ended with the first one, so the event must run again.
        assert await settings_of(engine) == ("off", "3s")
        assert await settings_of(engine) == ("off", "3s")
    finally:
        await engine.dispose()


async def test_settings_are_transaction_local(migrated_database_url: str) -> None:
    """Nothing leaks into the session, so a pooler can hand the connection to
    anyone (issue #37)."""
    engine = create_engine(migrated_database_url, EngineLimits(statement_timeout=3))
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            await connection.commit()
            raw = await connection.get_raw_connection()
            driver = raw.driver_connection
            assert driver is not None
            # Outside any transaction: the server's own defaults again.
            assert await driver.fetchval("SHOW statement_timeout") == "0"
            assert await driver.fetchval("SHOW jit") == "on"
    finally:
        await engine.dispose()


async def test_db_sync_runs_without_a_statement_budget(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    try:
        assert await settings_of(engine) == ("off", "0")
    finally:
        await engine.dispose()


async def test_a_slow_statement_is_cut_off(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url, EngineLimits(statement_timeout=0.2))
    try:
        with pytest.raises(StoreUnavailableError, match=r"^statement timeout$"):
            async with unavailable_as_store_error(), engine.connect() as connection:
                await connection.execute(text("SELECT pg_sleep(2)"))
        # The pool recovers: the next request is fine.
        assert await settings_of(engine) == ("off", "200ms")
    finally:
        await engine.dispose()


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


async def test_a_refused_connection_is_unavailable(
    real_catalog: IngredientCatalog,
) -> None:
    url = f"postgresql+asyncpg://u:p@127.0.0.1:{closed_port()}/app"
    engine = create_engine(url, EngineLimits(connect_timeout=1))
    repository = PostgresRecipeRepository(engine, real_catalog, max_core_q=1)
    try:
        with pytest.raises(StoreUnavailableError, match=r"^connection failed"):
            await repository.detail(SOME_RECIPE)
    finally:
        await engine.dispose()


async def test_an_exhausted_pool_is_unavailable_after_its_wait(
    seeded_database_url: str, real_catalog: IngredientCatalog
) -> None:
    limits = EngineLimits(pool_size=1, max_overflow=0, pool_timeout=0.2)
    engine = create_engine(seeded_database_url, limits)
    repository = await PostgresRecipeRepository.open(engine, real_catalog)
    try:
        async with engine.connect() as held:
            await held.execute(text("SELECT 1"))
            started = asyncio.get_running_loop().time()
            with pytest.raises(StoreUnavailableError, match=r"^pool timeout$"):
                await repository.detail(SOME_RECIPE)
            waited = asyncio.get_running_loop().time() - started
        assert 0.15 < waited < 1
        # Once the connection is back, the repository answers again.
        assert await repository.detail(SOME_RECIPE) is None
    finally:
        await engine.dispose()
