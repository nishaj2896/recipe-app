import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.infra.catalog_store import CatalogNotSyncedError, read_catalog

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
