"""The Task 2 gate, part 1: migrations go up and down cleanly (ADR-0005 rule 3)."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from recipe_app.infra.tables import metadata

ALEMBIC_INI = Path(__file__).parents[2] / "alembic.ini"
TABLES = {
    "alembic_version",
    "categories",
    "ingredients",
    "ingredient_search_terms",
    "recipes",
    "recipe_ingredients",
    "recipe_steps",
    "catalog_state",
}


def alembic_config(url: str) -> Config:
    config = Config(ALEMBIC_INI)
    config.attributes["url"] = url
    # Leave pytest's logging alone; env.py would otherwise reconfigure it.
    config.attributes["configure_logger"] = False
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


# Every constraint, index and column as Postgres itself prints it, so a changed
# CHECK expression, index or generated column shows up even when its name stays
# the same.
SCHEMA_OBJECTS = text(
    """
    SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid)
    FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace
    UNION ALL
    SELECT tablename, indexname, indexdef
    FROM pg_indexes
    WHERE schemaname = 'public'
    UNION ALL
    SELECT table_name, column_name, concat_ws(
        ' ', data_type, character_maximum_length, is_nullable,
        column_default, generation_expression
    )
    FROM information_schema.columns
    WHERE table_schema = 'public'
    """
)


def schema_objects(url: str) -> set[tuple[str, str, str]]:
    async def read() -> set[tuple[str, str, str]]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                rows = await connection.execute(SCHEMA_OBJECTS)
                return {(table, name, definition) for table, name, definition in rows}
        finally:
            await engine.dispose()

    return asyncio.run(read())


def create_all(url: str) -> None:
    async def create() -> None:
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(metadata.create_all)
        finally:
            await engine.dispose()

    asyncio.run(create())


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


def test_constraints_indexes_and_columns_match_tables_py(
    make_empty_database: Callable[[], str],
) -> None:
    """Catches what command.check can't, such as a CHECK whose expression changed."""
    migrated, created = make_empty_database(), make_empty_database()
    command.upgrade(alembic_config(migrated), "head")
    create_all(created)

    from_migrations = {
        row for row in schema_objects(migrated) if row[0] != "alembic_version"
    }
    assert from_migrations == schema_objects(created)
