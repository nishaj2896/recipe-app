from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.infra.catalog_store import CatalogNotSyncedError, read_catalog
from recipe_app.infra.sync import sync
from tests.domain.factories import catalog, category, ingredient

pytestmark = pytest.mark.anyio


async def test_the_synced_catalog_reads_back_unchanged(
    seeded_database_url: str, real_catalog: IngredientCatalog
) -> None:
    """Every category and ingredient, retired ones too, and the file's hash."""
    engine = create_async_engine(seeded_database_url)
    try:
        assert await read_catalog(engine) == real_catalog
    finally:
        await engine.dispose()


async def test_an_unsynced_database_has_no_catalog(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    try:
        with pytest.raises(CatalogNotSyncedError):
            await read_catalog(engine)
    finally:
        await engine.dispose()


async def test_allergens_and_jain_round_trip(migrated_database_url: str) -> None:
    flagged = parse_catalog(
        catalog(
            category(),
            ingredient(allergens=["sulphites", "gluten"]),
            ingredient(id="onion", name="Onion", jain=False),
        )
    )
    engine = create_async_engine(migrated_database_url)
    try:
        await sync(engine, flagged, [], now=datetime(2026, 11, 12, tzinfo=UTC))
        assert await read_catalog(engine) == flagged
    finally:
        await engine.dispose()
