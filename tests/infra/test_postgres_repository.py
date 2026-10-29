"""Postgres-only behaviour of the repository; the shared rules are in the contract."""

import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.content import Amount, Image, RecipeContent, RecipeWithContent
from recipe_app.domain.cursor import Position
from recipe_app.domain.matching import max_core_weight, resolve_pantry
from recipe_app.domain.ranking import Ranking, SearchFilters
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.domain.scoring import score_int
from recipe_app.domain.units import Unit
from recipe_app.infra.database import create_engine
from recipe_app.infra.postgres import PostgresRecipeRepository, reachable_core_q
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
    repository = await PostgresRecipeRepository.open(seeded_engine, real_catalog)

    for recipe in seed:
        detail = await repository.detail(recipe.id)
        assert detail is not None
        assert detail.recipe == recipe


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
    repository = await PostgresRecipeRepository.open(empty_engine, older)
    pantry = resolve_pantry(
        ingredient_ids=["potato"], excluded_staples=[], catalog=older
    )

    with caplog.at_level(logging.WARNING, logger="recipe_app"):
        assert await repository.detail(recipe_id) is None
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
    repository = await PostgresRecipeRepository.open(empty_engine, one)
    pantry = resolve_pantry(ingredient_ids=["potato"], excluded_staples=[], catalog=one)

    with caplog.at_level(logging.WARNING, logger="recipe_app"):
        assert await repository.detail(bare) is None
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
    repository = await PostgresRecipeRepository.open(empty_engine, older)
    pantry = resolve_pantry(
        ingredient_ids=["potato"], excluded_staples=[], catalog=older
    )

    with caplog.at_level(logging.WARNING, logger="recipe_app"):
        assert await repository.ranked(pantry, SearchFilters(), Position(), 20) == EMPTY

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
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
    repository = await PostgresRecipeRepository.open(empty_engine, loaded)
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


async def test_the_reachable_core_q_matches_the_domain(
    seeded_engine: AsyncEngine, seed: tuple[Recipe, ...]
) -> None:
    """The triangle is sized from SQL; the domain says what it must cover."""
    assert await reachable_core_q(seeded_engine) == max(map(max_core_weight, seed))


async def test_an_empty_database_reaches_no_core_q(empty_engine: AsyncEngine) -> None:
    assert await reachable_core_q(empty_engine) == 0


async def test_content_with_a_photo_and_a_to_taste_ingredient_round_trips(
    empty_engine: AsyncEngine,
) -> None:
    one = parse_catalog(
        catalog(
            category(),
            ingredient(),
            ingredient(id="salt", name="Salt", **{"class": "S"}, kind="pantry"),
        )
    )
    recipe = build_recipe(
        id=UUID(int=7),
        name="Salted potatoes",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato", "salt"],
        catalog=one,
    )
    content = RecipeContent(
        serves=2,
        amounts=(Amount(value=0.333, unit=Unit.KG), None),
        steps=("Boil the potatoes.", "Season and serve."),
        image=Image(file=f"{recipe.id}.webp", sha256="ab" * 32, alt="Potatoes"),
    )
    await sync(empty_engine, one, [recipe], now=NOW, content={recipe.id: content})
    repository = await PostgresRecipeRepository.open(empty_engine, one)

    assert await repository.detail(recipe.id) == RecipeWithContent(
        recipe=recipe, content=content
    )


async def test_a_recipe_synced_without_content_has_none(
    empty_engine: AsyncEngine,
) -> None:
    """Rows from before the ADR-0008 migration and sync have NULL serves."""
    one = parse_catalog(catalog(category(), ingredient()))
    recipe = build_recipe(
        id=UUID(int=8),
        name="Plain potatoes",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato"],
        catalog=one,
    )
    await sync(empty_engine, one, [recipe], now=NOW)
    repository = await PostgresRecipeRepository.open(empty_engine, one)

    assert await repository.detail(recipe.id) == RecipeWithContent(
        recipe=recipe, content=None
    )


async def test_detail_reads_one_version_while_a_sync_commits(
    empty_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sync committing between the recipe and its content can't mix versions.

    The sync here lands after the recipe's ingredients are read and before
    its amounts are: under READ COMMITTED the detail would pair two
    ingredients with one amount.
    """
    one = parse_catalog(
        catalog(category(), ingredient(), ingredient(id="onion", name="Onion"))
    )
    recipe = build_recipe(
        id=UUID(int=9),
        name="Onion potatoes",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato", "onion"],
        catalog=one,
    )
    content = RecipeContent(
        serves=2,
        amounts=(Amount(value=2, unit=Unit.MEDIUM), Amount(value=1, unit=Unit.SMALL)),
        steps=("Slice the onion.", "Fry it with the potatoes."),
        image=None,
    )
    await sync(empty_engine, one, [recipe], now=NOW, content={recipe.id: content})
    repository = await PostgresRecipeRepository.open(empty_engine, one)
    edited = replace(recipe, ingredients=recipe.ingredients[:1])
    edited_content = replace(content, amounts=content.amounts[:1])
    read_content = PostgresRecipeRepository._content

    async def sync_first(
        self: PostgresRecipeRepository, connection: AsyncConnection, recipe_id: UUID
    ) -> RecipeContent | None:
        await sync(
            empty_engine, one, [edited], now=NOW, content={recipe.id: edited_content}
        )
        return await read_content(self, connection, recipe_id)

    monkeypatch.setattr(PostgresRecipeRepository, "_content", sync_first)

    assert await repository.detail(recipe.id) == RecipeWithContent(
        recipe=recipe, content=content
    )
