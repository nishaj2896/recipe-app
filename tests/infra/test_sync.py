"""`recipe-app db sync` against a real database (ADR-0005 rule 2)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Table, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.matching import match_weight
from recipe_app.domain.recipe import Recipe
from recipe_app.infra import tables
from recipe_app.infra.database import create_engine
from recipe_app.infra.sync import SYNC_LOCK_KEY, SyncError, sync
from tests.domain.factories import catalog, category, ingredient

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
async def engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(migrated_database_url)
    yield engine
    await engine.dispose()


async def count(engine: AsyncEngine, table: Table) -> int:
    async with engine.connect() as connection:
        return await connection.scalar(select(func.count()).select_from(table)) or 0


async def test_sync_loads_every_file_row(
    engine: AsyncEngine, real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> None:
    report = await sync(engine, real_catalog, seed, now=NOW)

    assert report.recipes == len(seed)
    assert await count(engine, tables.categories) == len(real_catalog.categories)
    assert await count(engine, tables.ingredients) == len(real_catalog.by_id)
    assert await count(engine, tables.recipes) == len(seed)
    assert await count(engine, tables.recipe_ingredients) == sum(
        len(recipe.ingredients) for recipe in seed
    )
    async with engine.connect() as connection:
        stored_hash = await connection.scalar(
            select(tables.catalog_state.c.content_hash)
        )
    assert stored_hash == real_catalog.content_hash


async def test_stored_derived_columns_match_the_domain(
    engine: AsyncEngine, real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> None:
    """ADR-0005 rule 3: the stored derived columns agree with the domain."""
    await sync(engine, real_catalog, seed, now=NOW)

    async with engine.connect() as connection:
        rows = await connection.execute(
            select(
                tables.recipes.c.id,
                tables.recipes.c.diet,
                tables.recipes.c.all_staples,
                tables.recipes.c.total_minutes,
            )
        )
        stored = {
            row.id: (row.diet, row.all_staples, row.total_minutes) for row in rows
        }
    assert stored == {
        recipe.id: (recipe.diet.value, recipe.all_staples, recipe.total_minutes)
        for recipe in seed
    }


async def test_stored_weights_match_the_domain(
    engine: AsyncEngine, real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> None:
    """ADR-0007 rule 3: Postgres adds up the same weights the domain does."""
    await sync(engine, real_catalog, seed, now=NOW)

    async with engine.connect() as connection:
        weights = {
            (row.recipe_id, row.ingredient_id): row.weight
            for row in await connection.execute(
                select(
                    tables.recipe_ingredients.c.recipe_id,
                    tables.recipe_ingredients.c.ingredient_id,
                    tables.recipe_ingredients.c.weight,
                )
            )
        }
        core_weights = {
            row.id: row.core_weight
            for row in await connection.execute(
                select(tables.recipes.c.id, tables.recipes.c.core_weight)
            )
        }
    assert weights == {
        (recipe.id, item.id): match_weight(item)
        for recipe in seed
        for item in recipe.ingredients
    }
    assert core_weights == {
        recipe.id: sum(match_weight(item) for item in recipe.ingredients)
        for recipe in seed
    }


async def test_a_second_sync_changes_nothing(
    engine: AsyncEngine, real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> None:
    await sync(engine, real_catalog, seed, now=NOW)
    first = await snapshot(engine)

    await sync(engine, real_catalog, seed, now=NOW)

    assert await snapshot(engine) == first


async def test_removing_a_recipe_is_refused_and_writes_nothing(
    engine: AsyncEngine, real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> None:
    await sync(engine, real_catalog, seed, now=NOW)
    before = await snapshot(engine)

    with pytest.raises(SyncError, match=str(seed[0].id)):
        await sync(engine, real_catalog, seed[1:], now=NOW)

    assert await snapshot(engine) == before


async def test_removing_an_ingredient_is_refused(engine: AsyncEngine) -> None:
    two = parse_catalog(
        catalog(category(), ingredient(), ingredient(id="onion", name="Onion"))
    )
    await sync(engine, two, (), now=NOW)

    with pytest.raises(SyncError, match="ingredient 'onion'"):
        await sync(
            engine, parse_catalog(catalog(category(), ingredient())), (), now=NOW
        )


async def test_two_categories_can_swap_positions(engine: AsyncEngine) -> None:
    """The unique check on position runs at commit, not row by row."""

    def two_categories(vegetables: int, fruit: int) -> IngredientCatalog:
        return parse_catalog(
            catalog(
                category(position=vegetables),
                category(id="fruit", name="Fruit", position=fruit),
                ingredient(),
                ingredient(id="apple", name="Apple", category="fruit"),
            )
        )

    await sync(engine, two_categories(1, 2), (), now=NOW)
    await sync(engine, two_categories(2, 1), (), now=NOW)

    async with engine.connect() as connection:
        rows = await connection.execute(
            select(tables.categories.c.id, tables.categories.c.position)
        )
        assert {row.id: row.position for row in rows} == {"vegetables": 2, "fruit": 1}


async def test_a_sync_waits_while_another_holds_the_lock(
    engine: AsyncEngine, real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> None:
    async with engine.connect() as other:
        await other.execute(select(func.pg_advisory_lock(SYNC_LOCK_KEY)))
        waiting = asyncio.create_task(sync(engine, real_catalog, seed, now=NOW))
        await asyncio.sleep(0.5)  # far longer than a sync of the seed takes
        assert not waiting.done()

        await other.execute(select(func.pg_advisory_unlock(SYNC_LOCK_KEY)))
        await waiting

    assert await count(engine, tables.recipes) == len(seed)


async def snapshot(engine: AsyncEngine) -> dict[str, list[tuple[object, ...]]]:
    """Every row of every table, sorted, so two snapshots compare with ==."""
    async with engine.connect() as connection:
        return {
            table.name: sorted(
                (tuple(row) for row in await connection.execute(select(table))),
                key=repr,
            )
            for table in tables.metadata.sorted_tables
        }
