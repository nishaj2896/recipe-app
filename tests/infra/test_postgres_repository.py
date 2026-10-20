"""Postgres-only behaviour of the repository; the shared rules are in the contract."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.infra.database import create_engine
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.infra.sync import sync
from tests.domain.factories import catalog, category, ingredient

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
async def seeded_engine(seeded_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(seeded_database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def empty_engine(migrated_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(migrated_database_url)
    yield engine
    await engine.dispose()


async def test_every_seed_recipe_round_trips(
    seeded_engine: AsyncEngine,
    real_catalog: IngredientCatalog,
    seed: tuple[Recipe, ...],
) -> None:
    """Same fields, same ingredients, in the same order the file lists them."""
    repository = PostgresRecipeRepository(seeded_engine, real_catalog)

    for recipe in seed:
        assert await repository.get(recipe.id) == recipe


async def test_a_recipe_using_an_ingredient_this_catalog_lacks_is_skipped(
    empty_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-0005: a pod that loaded its catalog before a sync skips and logs it."""
    newer = parse_catalog(
        catalog(category(), ingredient(), ingredient(id="onion", name="Onion"))
    )
    older = parse_catalog(catalog(category(), ingredient()))
    recipe_id = UUID(int=1)
    recipe = build_recipe(
        id=recipe_id,
        name="Onion potatoes",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato", "onion"],
        catalog=newer,
    )
    await sync(empty_engine, newer, [recipe], now=NOW)
    repository = PostgresRecipeRepository(empty_engine, older)
    pantry = resolve_pantry(
        ingredient_ids=["potato"], excluded_staples=[], catalog=older
    )

    with caplog.at_level(logging.WARNING, logger="recipe_app"):
        assert await repository.get(recipe_id) is None
        assert await repository.candidates(pantry, SearchFilters()) == []

    assert "ingredients ['onion'] are not in catalog" in caplog.text
