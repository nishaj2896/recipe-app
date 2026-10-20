import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
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
    """Creates new, empty databases on demand and drops them all after the test.

    Skips when TEST_DATABASE_URL isn't set, except in CI, where a skipped
    database test would hide a broken migration.
    """
    server = os.environ.get(TEST_DATABASE_URL_VARIABLE)
    if not server:
        if os.environ.get("CI"):
            pytest.fail(f"{TEST_DATABASE_URL_VARIABLE} must be set in CI")
        pytest.skip(f"set {TEST_DATABASE_URL_VARIABLE} to run the database tests")
    created: list[str] = []

    def make() -> str:
        name = f"test_{uuid4().hex[:12]}"
        asyncio.run(_admin(server, f'CREATE DATABASE "{name}"'))
        created.append(name)
        return make_url(server).set(database=name).render_as_string(hide_password=False)

    try:
        yield make
    finally:
        for name in created:
            asyncio.run(_admin(server, f'DROP DATABASE "{name}" WITH (FORCE)'))


@pytest.fixture
def empty_database_url(make_empty_database: Callable[[], str]) -> str:
    """The URL of a new, empty database, dropped after the test."""
    return make_empty_database()


@pytest.fixture
def migrated_database_url(empty_database_url: str) -> str:
    """A new database with every migration applied, dropped after the test."""
    config = Config(ALEMBIC_INI)
    config.attributes["url"] = empty_database_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return empty_database_url


async def _admin(url: str, statement: str) -> None:
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()
