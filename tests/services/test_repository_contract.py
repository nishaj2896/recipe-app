"""The RecipeRepository contract. Every adapter runs these.

The seed loads at import, not in a fixture, because the Hypothesis strategies
below need its ingredient ids when the module is collected.
"""

import asyncio
from collections.abc import Iterator
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from recipe_app.domain.catalog import Diet, IngredientClass
from recipe_app.domain.cursor import Position
from recipe_app.domain.deck import Deck, position_after
from recipe_app.domain.matching import AllStaplesMatch, ScoredMatch, resolve_pantry
from recipe_app.domain.ranking import SearchFilters, rank
from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.services.ports import RecipeRepository
from tests.domain.factories import DATA_DIR

CATALOG = load_catalog(DATA_DIR)
SEED = load_recipes(CATALOG, DATA_DIR)
STAPLE = IngredientClass.STAPLE
USED = sorted({item.id for recipe in SEED for item in recipe.ingredients})
CORE_IDS = [i for i in USED if CATALOG.by_id[i].ingredient_class is not STAPLE]
STAPLE_IDS = [i for i in USED if CATALOG.by_id[i].ingredient_class is STAPLE]


@pytest.fixture(scope="module", params=["memory", "postgres"])
def repository(request: pytest.FixtureRequest) -> Iterator[RecipeRepository]:
    """Each adapter over the seed. Module scope, so Hypothesis can use it."""
    if request.param == "memory":
        yield InMemoryRecipeRepository(SEED)
        return
    url: str = request.getfixturevalue("seeded_database_url")
    # No pool: every test step runs in its own event loop via asyncio.run, and
    # a pooled asyncpg connection can't move between loops.
    engine = create_async_engine(url, poolclass=NullPool)
    yield PostgresRecipeRepository(engine, CATALOG)
    asyncio.run(engine.dispose())


def test_get_returns_the_recipe(repository: RecipeRepository) -> None:
    assert asyncio.run(repository.get(SEED[0].id)) == SEED[0]


def test_get_unknown_id_returns_none(repository: RecipeRepository) -> None:
    assert asyncio.run(repository.get(UUID(int=0))) is None


@settings(max_examples=200, deadline=None)
@given(
    # Staple ids too: a request of only staples leaves pantry.have empty, and
    # then only the all-staples recipes can show.
    have=st.lists(
        st.sampled_from(CORE_IDS + STAPLE_IDS), min_size=1, max_size=8, unique=True
    ),
    out_of=st.lists(st.sampled_from(STAPLE_IDS), max_size=4, unique=True),
    diet=st.none() | st.sampled_from(Diet),
    max_total_minutes=st.none() | st.integers(1, 600),
    hidden=st.sets(st.sampled_from([recipe.id for recipe in SEED]), max_size=5),
    limit=st.integers(1, 8),
)
def test_ranked_pages_through_exactly_the_domain_ranking(
    repository: RecipeRepository,
    have: list[str],
    out_of: list[str],
    diet: Diet | None,
    max_total_minutes: int | None,
    hidden: set[UUID],
    limit: int,
) -> None:
    """Walking every page gives the domain's ranking of every recipe, in order
    (ADR-0007 rule 6). Small pages, so the keyset resume runs many times.
    """
    pantry = resolve_pantry(
        ingredient_ids=have, excluded_staples=out_of, catalog=CATALOG
    )
    filters = SearchFilters(
        diet=diet,
        max_total_minutes=max_total_minutes,
        hidden_recipe_ids=frozenset(hidden),
    )
    expected = rank(SEED, pantry, filters)

    scored: list[ScoredMatch] = []
    all_staples: list[AllStaplesMatch] = []
    after = Position()
    for _ in range(len(SEED) + 1):
        page = asyncio.run(repository.ranked(pantry, filters, after, limit))
        assert len(page.scored) <= limit
        assert len(page.all_staples) <= limit
        if not (page.scored or page.all_staples):
            break
        scored += page.scored
        all_staples += page.all_staples
        after = position_after(Deck(page.scored, page.all_staples), after)

    assert scored == list(expected.scored)
    assert all_staples == list(expected.all_staples)


def test_ranked_applies_the_filters(repository: RecipeRepository) -> None:
    pantry = resolve_pantry(
        ingredient_ids=CORE_IDS, excluded_staples=[], catalog=CATALOG
    )
    filters = SearchFilters(diet=Diet.VEGAN, max_total_minutes=20)

    page = asyncio.run(repository.ranked(pantry, filters, Position(), 20))
    shown = [m.recipe for m in page.scored] + [m.recipe for m in page.all_staples]

    assert shown
    assert all(recipe.diet is Diet.VEGAN for recipe in shown)
    assert all(recipe.total_minutes <= 20 for recipe in shown)
