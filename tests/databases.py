"""Throwaway test databases on the server TEST_DATABASE_URL names.

Shared by the conftests that build database fixtures.
"""

import asyncio
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.content import RecipeContent
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.sync import sync

TEST_DATABASE_URL_VARIABLE = "TEST_DATABASE_URL"
ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


def database_server() -> str:
    """TEST_DATABASE_URL; skips without it, except in CI, where a skipped
    database test would hide a broken migration.
    """
    server = os.environ.get(TEST_DATABASE_URL_VARIABLE)
    if not server:
        if os.environ.get("CI"):
            pytest.fail(f"{TEST_DATABASE_URL_VARIABLE} must be set in CI")
        pytest.skip(f"set {TEST_DATABASE_URL_VARIABLE} to run the database tests")
    return server


def create_database(server: str) -> str:
    name = f"test_{uuid4().hex[:12]}"
    asyncio.run(admin(server, f'CREATE DATABASE "{name}"'))
    return make_url(server).set(database=name).render_as_string(hide_password=False)


def drop_database(server: str, url: str) -> None:
    name = make_url(url).database
    asyncio.run(admin(server, f'DROP DATABASE "{name}" WITH (FORCE)'))


def migrate(url: str) -> None:
    config = Config(ALEMBIC_INI)
    config.attributes["url"] = url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


async def sync_seed(
    url: str,
    catalog: IngredientCatalog,
    recipes: tuple[Recipe, ...],
    content: Mapping[UUID, RecipeContent] = MappingProxyType({}),
) -> None:
    engine = create_async_engine(url)
    try:
        await sync(engine, catalog, recipes, now=datetime.now(UTC), content=content)
    finally:
        await engine.dispose()


async def admin(url: str, statement: str) -> None:
    # CREATE/DROP DATABASE can't run inside a transaction, hence AUTOCOMMIT.
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await connection.execute(text(statement))
    finally:
        await engine.dispose()
