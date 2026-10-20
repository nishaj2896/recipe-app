"""The Task 2 gate, part 1: migrations go up and down cleanly (ADR-0005 rule 3)."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
TABLES = {
    "alembic_version",
    "categories",
    "ingredients",
    "ingredient_search_terms",
    "recipes",
    "recipe_ingredients",
    "catalog_state",
}


def alembic_config(url: str) -> Config:
    config = Config(ALEMBIC_INI)
    config.attributes["url"] = url
    return config


def table_names(url: str) -> set[str]:
    async def read() -> set[str]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync: set(inspect(sync).get_table_names())
                )
        finally:
            await engine.dispose()

    return asyncio.run(read())


def test_migrations_go_up_down_and_up_again(empty_database_url: str) -> None:
    config = alembic_config(empty_database_url)

    command.upgrade(config, "head")
    assert table_names(empty_database_url) == TABLES

    command.downgrade(config, "base")
    assert table_names(empty_database_url) == {"alembic_version"}

    command.upgrade(config, "head")
    assert table_names(empty_database_url) == TABLES


def test_tables_py_matches_the_migrations(empty_database_url: str) -> None:
    """Fails when someone edits tables.py and forgets the migration, or the reverse."""
    config = alembic_config(empty_database_url)
    command.upgrade(config, "head")

    command.check(config)  # raises if autogenerate would write anything
