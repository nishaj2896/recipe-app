import asyncio
from collections.abc import Iterator
from dataclasses import replace

import pytest
from sqlalchemy import text

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.database import create_engine
from tests.databases import (
    create_database,
    database_server,
    drop_database,
    migrate,
    sync_seed,
)
from tests.gate.searches import gate_recipes


@pytest.fixture(scope="session")
def gate_seed(
    real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]
) -> tuple[Recipe, ...]:
    # The gate syncs recipes without their content, so Postgres holds no photos.
    return gate_recipes(real_catalog, [replace(recipe, image=None) for recipe in seed])


@pytest.fixture(scope="session")
def gate_database_url(
    real_catalog: IngredientCatalog, gate_seed: tuple[Recipe, ...]
) -> Iterator[str]:
    """50,000 recipes, analyzed, so the planner sees production-sized tables."""
    server = database_server()
    url = create_database(server)
    try:
        migrate(url)
        asyncio.run(sync_seed(url, real_catalog, gate_seed))
        asyncio.run(_analyze(url))
        yield url
    finally:
        drop_database(server, url)


async def _analyze(url: str) -> None:
    # Autovacuum would get there, but not before the tests read the plans.
    engine = create_engine(url)
    try:
        # begin(), not connect(): a rolled-back ANALYZE keeps no statistics.
        async with engine.begin() as connection:
            await connection.execute(text("ANALYZE"))
    finally:
        await engine.dispose()
