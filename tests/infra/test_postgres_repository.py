"""Postgres-only behaviour of the repository; the shared rules are in the contract."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.cursor import Position
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.ranking import Ranking, SearchFilters
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.domain.scoring import score_int
from recipe_app.infra.database import create_engine
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.infra.sync import sync
from recipe_app.infra.tables import recipes
from tests.domain.factories import catalog, category, ingredient

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
EMPTY = Ranking(scored=(), all_staples=())


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
        assert await repository.ranked(pantry, SearchFilters(), Position(), 20) == EMPTY

    assert "unknown ingredients ['onion']" in caplog.text


async def test_a_recipe_with_no_ingredient_rows_is_skipped_not_fatal(
    empty_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """Only a bug or a manual edit leaves one, but it costs that recipe, not search."""
    one = parse_catalog(catalog(category(), ingredient()))
    kept = build_recipe(
        id=UUID(int=1),
        name="Boiled potatoes",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato"],
        catalog=one,
    )
    await sync(empty_engine, one, [kept], now=NOW)
    bare = UUID(int=2)
    async with empty_engine.begin() as connection:
        await connection.execute(
            insert(recipes).values(
                id=bare,
                name="Bare",
                prep_minutes=1,
                cook_minutes=1,
                diet="vegan",
                all_staples=True,
                core_weight=0,
            )
        )
    repository = PostgresRecipeRepository(empty_engine, one)
    pantry = resolve_pantry(ingredient_ids=["potato"], excluded_staples=[], catalog=one)

    with caplog.at_level(logging.WARNING, logger="recipe_app"):
        assert await repository.get(bare) is None
        ranked = await repository.ranked(pantry, SearchFilters(), Position(), 20)
        assert [match.recipe for match in ranked.scored] == [kept]

    assert str(bare) in caplog.text


async def test_skipped_recipes_log_one_warning_per_call(
    empty_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    newer = parse_catalog(
        catalog(category(), ingredient(), ingredient(id="onion", name="Onion"))
    )
    older = parse_catalog(catalog(category(), ingredient()))
    onion_recipes = [
        build_recipe(
            id=UUID(int=number),
            name=f"Onion potatoes {number}",
            prep_minutes=5,
            cook_minutes=20,
            ingredient_ids=["potato", "onion"],
            catalog=newer,
        )
        for number in range(1, 4)
    ]
    await sync(empty_engine, newer, onion_recipes, now=NOW)
    repository = PostgresRecipeRepository(empty_engine, older)
    pantry = resolve_pantry(
        ingredient_ids=["potato"], excluded_staples=[], catalog=older
    )

    with caplog.at_level(logging.WARNING, logger="recipe_app"):
        assert await repository.ranked(pantry, SearchFilters(), Position(), 20) == EMPTY

    assert len(caplog.records) == 1
    assert "skipped 3 recipes" in caplog.text


async def test_a_score_postgres_and_the_domain_disagree_on_is_logged_and_served(
    empty_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-0007 rule 5: a sync reclassified potato before this pod restarted."""
    synced = parse_catalog(
        catalog(category(), ingredient(), ingredient(id="peas", name="Peas"))
    )
    loaded = parse_catalog(
        catalog(
            category(),
            ingredient(**{"class": "B"}),
            ingredient(id="peas", name="Peas"),
        )
    )
    recipe = build_recipe(
        id=UUID(int=1),
        name="Potatoes and peas",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato", "peas"],
        catalog=synced,
    )
    await sync(empty_engine, synced, [recipe], now=NOW)
    repository = PostgresRecipeRepository(empty_engine, loaded)
    pantry = resolve_pantry(
        ingredient_ids=["potato"], excluded_staples=[], catalog=loaded
    )

    with caplog.at_level(logging.ERROR, logger="recipe_app"):
        ranked = await repository.ranked(pantry, SearchFilters(), Position(), 20)

    [card] = ranked.scored
    assert card.recipe.id == recipe.id
    assert f"recipe {recipe.id}: postgres ranked it as scored" in caplog.text
    # Postgres's score, so the cursor resumes where Postgres stopped (rule 5).
    assert card.score_int == score_int(4, 8)


async def test_a_recipe_past_the_score_triangle_ranks_last_not_missing(
    empty_engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-0007 rule 4: a sync added a bigger recipe before this pod restarted."""
    one = parse_catalog(
        catalog(category(), ingredient(), ingredient(id="peas", name="Peas"))
    )
    small, large = (
        build_recipe(
            id=UUID(int=number),
            name=name,
            prep_minutes=5,
            cook_minutes=20,
            ingredient_ids=ingredients,
            catalog=one,
        )
        for number, name, ingredients in (
            (1, "Potatoes", ["potato"]),
            (2, "Potatoes and peas", ["potato", "peas"]),
        )
    )
    await sync(empty_engine, one, [small, large], now=NOW)
    # Covers core_q 4 (potato), not 8 (potato and peas).
    repository = PostgresRecipeRepository(empty_engine, one, max_core_q=4)
    pantry = resolve_pantry(
        ingredient_ids=["potato", "peas"], excluded_staples=[], catalog=one
    )

    with caplog.at_level(logging.ERROR, logger="recipe_app"):
        ranked = await repository.ranked(pantry, SearchFilters(), Position(), 20)

    assert [card.recipe.id for card in ranked.scored] == [small.id, large.id]
    assert f"recipe {large.id}: postgres ranked it as scored -1" in caplog.text
