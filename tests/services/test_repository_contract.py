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
from recipe_app.domain.content import RecipeWithContent
from recipe_app.domain.cursor import Position
from recipe_app.domain.deck import Deck, position_after
from recipe_app.domain.matching import AllStaplesMatch, ScoredMatch, resolve_pantry
from recipe_app.domain.ranking import SearchFilters, rank
from recipe_app.domain.recipe_search import QueryResolver, find
from recipe_app.domain.tags import Allergen, Course, Mood, Weather
from recipe_app.infra.data import load_catalog, load_recipe_book
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.services.ports import RecipeRepository
from tests.domain.factories import DATA_DIR

CATALOG = load_catalog(DATA_DIR)
BOOK = load_recipe_book(CATALOG, DATA_DIR)
SEED = BOOK.recipes
STAPLE = IngredientClass.STAPLE
USED = sorted({item.id for recipe in SEED for item in recipe.ingredients})
CORE_IDS = [i for i in USED if CATALOG.by_id[i].ingredient_class is not STAPLE]
STAPLE_IDS = [i for i in USED if CATALOG.by_id[i].ingredient_class is STAPLE]


@pytest.fixture(scope="module", params=["memory", "postgres"])
def repository(request: pytest.FixtureRequest) -> Iterator[RecipeRepository]:
    """Each adapter over the seed. Module scope, so Hypothesis can use it."""
    if request.param == "memory":
        yield InMemoryRecipeRepository(SEED, BOOK.content)
        return
    url: str = request.getfixturevalue("seeded_database_url")
    # No pool: every test step runs in its own event loop via asyncio.run, and
    # a pooled asyncpg connection can't move between loops.
    engine = create_async_engine(url, poolclass=NullPool)
    yield asyncio.run(PostgresRecipeRepository.open(engine, CATALOG))
    asyncio.run(engine.dispose())


def test_detail_round_trips_for_every_recipe(repository: RecipeRepository) -> None:
    """Same recipe; amounts survive numeric(9, 3), and steps, amounts and
    pairings keep their order.
    """
    by_id = {recipe.id: recipe for recipe in SEED}
    for recipe in SEED:
        assert asyncio.run(repository.detail(recipe.id)) == RecipeWithContent(
            recipe=recipe,
            content=BOOK.content[recipe.id],
            pairs=tuple(by_id[pair] for pair in recipe.tags.pairs_with),
        )


def test_detail_of_unknown_id_is_none(repository: RecipeRepository) -> None:
    assert asyncio.run(repository.detail(UUID(int=0))) is None


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
    min_total_minutes=st.none() | st.integers(1, 90),
    jain=st.booleans(),
    avoid_allergens=st.frozensets(st.sampled_from(Allergen), max_size=3),
    avoid_ingredient_ids=st.frozensets(st.sampled_from(USED), max_size=3),
    courses=st.frozensets(st.sampled_from(Course), max_size=3),
    moods=st.frozensets(st.sampled_from(Mood), max_size=3),
    weather=st.frozensets(st.sampled_from(Weather), max_size=3),
)
def test_ranked_pages_through_exactly_the_domain_ranking(
    repository: RecipeRepository,
    have: list[str],
    out_of: list[str],
    diet: Diet | None,
    max_total_minutes: int | None,
    hidden: set[UUID],
    limit: int,
    min_total_minutes: int | None,
    jain: bool,
    avoid_allergens: frozenset[Allergen],
    avoid_ingredient_ids: frozenset[str],
    courses: frozenset[Course],
    moods: frozenset[Mood],
    weather: frozenset[Weather],
) -> None:
    """Walking every page gives the domain's ranking of every recipe, in order
    (ADR-0007 rule 6), with every filter and mood pick (ADR-0012 rules 4 to
    6). Small pages, so the keyset resume runs many times.
    """
    pantry = resolve_pantry(
        ingredient_ids=have, excluded_staples=out_of, catalog=CATALOG
    )
    filters = SearchFilters(
        diet=diet,
        max_total_minutes=max_total_minutes,
        hidden_recipe_ids=frozenset(hidden),
        min_total_minutes=min_total_minutes,
        jain=jain,
        avoid_allergens=avoid_allergens,
        avoid_ingredient_ids=avoid_ingredient_ids,
        courses=courses,
        moods=moods,
        weather=weather,
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


def test_ranked_applies_the_food_rules(repository: RecipeRepository) -> None:
    pantry = resolve_pantry(
        ingredient_ids=CORE_IDS, excluded_staples=[], catalog=CATALOG
    )
    filters = SearchFilters(
        diet=Diet.VEGETARIAN,
        jain=True,
        avoid_allergens=frozenset({Allergen.PEANUTS}),
        avoid_ingredient_ids=frozenset({"coconut-milk"}),
        min_total_minutes=20,
    )

    page = asyncio.run(repository.ranked(pantry, filters, Position(), 20))
    shown = [m.recipe for m in page.scored] + [m.recipe for m in page.all_staples]

    assert shown
    for recipe in shown:
        assert recipe.jain
        assert Allergen.PEANUTS not in recipe.allergens
        assert "coconut-milk" not in {item.id for item in recipe.ingredients}
        assert recipe.total_minutes >= 20


def test_ranked_puts_the_best_fit_first(repository: RecipeRepository) -> None:
    pantry = resolve_pantry(
        ingredient_ids=CORE_IDS, excluded_staples=[], catalog=CATALOG
    )
    filters = SearchFilters(
        courses=frozenset({Course.MAINS}),
        moods=frozenset({Mood.SPICY, Mood.TANGY}),
        weather=frozenset({Weather.RAINY_DAY_COSY}),
    )

    page = asyncio.run(repository.ranked(pantry, filters, Position(), 20))

    assert page.scored
    for match in page.scored:
        assert Course.MAINS in match.recipe.tags.courses
        assert {Mood.SPICY, Mood.TANGY} & set(match.recipe.tags.moods)
    fits = [m.fit for m in page.scored]
    assert fits == sorted(fits, reverse=True)
    # Spicy, tangy and rainy-day cosy all at once leads the seed's mains.
    assert fits[0] == 3
    assert fits[-1] < 3


def _typed_texts() -> list[str]:
    """What people type: name and word starts, misspellings, ingredients
    and cuisines, drawn from the seed so every criterion is exercised.
    """
    texts: set[str] = {"thai", "south asian", "middle", "aloo", "xq"}
    for recipe in SEED[::7]:
        name = recipe.name.lower()
        texts.update({name[:2], name[:5], name})
        words = name.split()
        if len(words) > 1:
            texts.add(words[-1][:4])
        if len(name) > 4:
            texts.add(name[:2] + name[3:])  # one letter dropped
            texts.add(name[:3] + name[2:])  # one letter doubled
    for item in list(CATALOG.by_id.values())[::25]:
        texts.add(item.name.lower()[:6])
    return sorted(t for t in texts if len(t) >= 2)


TYPED = _typed_texts()
RESOLVER = QueryResolver(CATALOG)


@settings(max_examples=150, deadline=None)
@given(
    text=st.sampled_from(TYPED),
    limit=st.integers(1, 20),
    offset=st.integers(0, 40),
)
def test_find_is_exactly_the_domain_search(
    repository: RecipeRepository, text: str, limit: int, offset: int
) -> None:
    """Postgres's trigram, LIKE and ingredient matches rank exactly as
    recipe_search.find does (ADR-0012 rule 10).
    """
    query = RESOLVER.resolve(text)

    assert asyncio.run(repository.find(query, limit, offset)) == find(
        SEED, query, limit, offset
    )


def test_find_past_the_last_match_still_counts_them(
    repository: RecipeRepository,
) -> None:
    query = RESOLVER.resolve("paneer")
    total = find(SEED, query, 1, 0).total

    found = asyncio.run(repository.find(query, 20, total))

    assert found.recipes == ()
    assert found.total == total > 0
