import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from recipe_app.api.app import create_app
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.cursor import SigningKeys
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.infra.sync import sync
from recipe_app.services.search import RecipeService
from tests.apps import KEYS, NOW, AppFactory, client_for
from tests.domain.factories import DATA_DIR

TEST_DATABASE_URL_VARIABLE = "TEST_DATABASE_URL"
ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


@pytest.fixture(scope="session")
def real_catalog() -> IngredientCatalog:
    return load_catalog(DATA_DIR)


@pytest.fixture(scope="session")
def seed(real_catalog: IngredientCatalog) -> tuple[Recipe, ...]:
    return load_recipes(real_catalog, DATA_DIR)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_app(real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]) -> AppFactory:
    """An app over the real catalog; pass recipes, keys or a clock to change one."""

    def make(
        *,
        recipes: tuple[Recipe, ...] = seed,
        catalog: IngredientCatalog = real_catalog,
        keys: SigningKeys = KEYS,
        now: int = NOW,
    ) -> FastAPI:
        service = RecipeService(
            catalog=catalog,
            repository=InMemoryRecipeRepository(recipes),
            keys=keys,
            clock=lambda: now,
        )
        return create_app(catalog=catalog, service=service)

    return make


@pytest.fixture
async def client(make_app: AppFactory) -> AsyncIterator[AsyncClient]:
    async with client_for(make_app()) as c:
        yield c


@pytest.fixture
def make_empty_database() -> Iterator[Callable[[], str]]:
    """Creates new, empty databases on demand and drops them all after the test."""
    server = _database_server()
    created: list[str] = []

    def make() -> str:
        url = _create_database(server)
        created.append(url)
        return url

    try:
        yield make
    finally:
        for url in created:
            _drop_database(server, url)


@pytest.fixture
def empty_database_url(make_empty_database: Callable[[], str]) -> str:
    """The URL of a new, empty database, dropped after the test."""
    return make_empty_database()


@pytest.fixture
def migrated_database_url(empty_database_url: str) -> str:
    """A new database with every migration applied, dropped after the test."""
    _migrate(empty_database_url)
    return empty_database_url


@pytest.fixture(scope="session")
def seeded_database_url(
    real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> Iterator[str]:
    """One migrated database holding the seed, shared by tests that only read it."""
    server = _database_server()
    url = _create_database(server)
    try:
        _migrate(url)
        asyncio.run(_sync_seed(url, real_catalog, seed))
        yield url
    finally:
        _drop_database(server, url)


def _database_server() -> str:
    """TEST_DATABASE_URL; skips without it, except in CI, where a skipped
    database test would hide a broken migration.
    """
    server = os.environ.get(TEST_DATABASE_URL_VARIABLE)
    if not server:
        if os.environ.get("CI"):
            pytest.fail(f"{TEST_DATABASE_URL_VARIABLE} must be set in CI")
        pytest.skip(f"set {TEST_DATABASE_URL_VARIABLE} to run the database tests")
    return server


def _create_database(server: str) -> str:
    name = f"test_{uuid4().hex[:12]}"
    asyncio.run(_admin(server, f'CREATE DATABASE "{name}"'))
    return make_url(server).set(database=name).render_as_string(hide_password=False)


def _drop_database(server: str, url: str) -> None:
    name = make_url(url).database
    asyncio.run(_admin(server, f'DROP DATABASE "{name}" WITH (FORCE)'))


def _migrate(url: str) -> None:
    config = Config(ALEMBIC_INI)
    config.attributes["url"] = url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


async def _sync_seed(
    url: str, catalog: IngredientCatalog, recipes: tuple[Recipe, ...]
) -> None:
    engine = create_async_engine(url)
    try:
        await sync(engine, catalog, recipes, now=datetime.now(UTC))
    finally:
        await engine.dispose()


async def _admin(url: str, statement: str) -> None:
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()
