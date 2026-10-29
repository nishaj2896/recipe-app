"""Property-based tests on the scoring and paging rules (the Task 3 gate).

Hypothesis draws recipes, pantries and swipe sessions over the real catalog,
so these hold for inputs nobody wrote down, not just the gate's examples.
They pin today's behaviour before ranking moves into Postgres (ADR-0007).
"""

import asyncio
from collections.abc import Sequence
from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from recipe_app.domain.catalog import IngredientClass
from recipe_app.domain.deck import MAX_ALL_STAPLES_WITH_SCORED, MAX_DECK_SIZE
from recipe_app.domain.matching import (
    AllStaplesMatch,
    Pantry,
    ScoredMatch,
    match_recipe,
    resolve_pantry,
)
from recipe_app.domain.ranking import SearchFilters, rank
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.domain.scoring import match_tenths, score_int
from recipe_app.infra.data import load_catalog
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.services.search import RecipeService, SearchQuery
from tests.apps import KEYS, NOW
from tests.domain.factories import DATA_DIR

CATALOG = load_catalog(DATA_DIR)
LIVE = sorted(item.id for item in CATALOG.by_id.values() if not item.retired)
CORE_IDS = [
    i for i in LIVE if CATALOG.by_id[i].ingredient_class is not IngredientClass.STAPLE
]
STAPLE_IDS = [
    i for i in LIVE if CATALOG.by_id[i].ingredient_class is IngredientClass.STAPLE
]
# A small slice of the catalog, so drawn recipes and pantries overlap often.
CORE_POOL = CORE_IDS[:12]
STAPLE_POOL = STAPLE_IDS[:8]

FULL_TENTHS = 1000  # 100.0%

core_weights = st.integers(1, 200)


@st.composite
def weight_pairs(draw: st.DrawFn) -> tuple[int, int]:
    core_q = draw(core_weights)
    return draw(st.integers(1, core_q)), core_q


@st.composite
def recipes(draw: st.DrawFn, ids: st.SearchStrategy[UUID]) -> Recipe:
    prep = draw(st.integers(0, 60))
    return build_recipe(
        id=draw(ids),
        name="Recipe",
        prep_minutes=prep,
        cook_minutes=draw(st.integers(1 if prep == 0 else 0, 60)),
        ingredient_ids=draw(
            st.lists(
                st.sampled_from(CORE_POOL + STAPLE_POOL),
                min_size=1,
                max_size=8,
                unique=True,
            )
        ),
        catalog=CATALOG,
    )


def recipe_sets(max_size: int = 40) -> st.SearchStrategy[list[Recipe]]:
    # Few distinct ids, so the id tie-break in the sort key gets exercised.
    return st.lists(
        recipes(st.integers(1, 10_000).map(lambda n: UUID(int=n))),
        max_size=max_size,
        unique_by=lambda recipe: recipe.id,
    )


@st.composite
def pantries(draw: st.DrawFn) -> Pantry:
    return resolve_pantry(
        ingredient_ids=draw(
            st.lists(st.sampled_from(CORE_POOL), min_size=1, max_size=8, unique=True)
        ),
        excluded_staples=draw(
            st.lists(st.sampled_from(STAPLE_POOL), max_size=3, unique=True)
        ),
        catalog=CATALOG,
    )


# Scoring (ADR-0003 rules 4 and 8)


@given(weight_pairs())
def test_the_percentage_is_100_only_when_everything_matched(
    pair: tuple[int, int],
) -> None:
    matched_q, core_q = pair
    tenths = match_tenths(matched_q, core_q)

    assert 0 < tenths <= FULL_TENTHS
    assert (tenths == FULL_TENTHS) == (matched_q == core_q)


@given(weight_pairs())
def test_more_matched_weight_never_lowers_the_score(pair: tuple[int, int]) -> None:
    matched_q, core_q = pair
    if matched_q < core_q:
        assert score_int(matched_q + 1, core_q) > score_int(matched_q, core_q)
        assert match_tenths(matched_q + 1, core_q) >= match_tenths(matched_q, core_q)


@given(weight_pairs())
def test_a_larger_core_never_raises_the_score(pair: tuple[int, int]) -> None:
    """Missing one more ingredient is never a reward."""
    matched_q, core_q = pair
    assert score_int(matched_q, core_q + 1) <= score_int(matched_q, core_q)


# Matching (ADR-0003 rules 2 and 3)


@given(recipes(st.just(UUID(int=1))), pantries())
def test_every_ingredient_is_matched_missing_or_assumed_exactly_once(
    recipe: Recipe, pantry: Pantry
) -> None:
    match = match_recipe(recipe, pantry)
    if match is None:
        return
    shown = list(match.assumed)
    if isinstance(match, ScoredMatch):
        shown += [*match.matched, *match.missing]

    assert sorted(item.id for item in shown) == sorted(
        item.id for item in recipe.ingredients
    )


@given(recipes(st.just(UUID(int=1))), pantries())
def test_staples_are_missing_exactly_when_unticked(
    recipe: Recipe, pantry: Pantry
) -> None:
    match = match_recipe(recipe, pantry)
    if not isinstance(match, ScoredMatch):
        return
    missing = {item.id for item in match.missing}

    for item in recipe.ingredients:
        if item.ingredient_class is IngredientClass.STAPLE:
            assert (item.id in missing) == (item.id in pantry.out_of)
    assert not {item.id for item in match.matched} & set(STAPLE_IDS)


@given(recipes(st.just(UUID(int=1))), pantries())
def test_a_full_percentage_means_nothing_is_missing(
    recipe: Recipe, pantry: Pantry
) -> None:
    match = match_recipe(recipe, pantry)
    if isinstance(match, ScoredMatch):
        assert (match.match_tenths == FULL_TENTHS) == (not match.missing)


@given(recipe_sets(), pantries(), st.sampled_from(CORE_POOL))
def test_adding_an_ingredient_never_drops_a_recipe_or_a_match(
    recipes: list[Recipe], pantry: Pantry, extra: str
) -> None:
    more = resolve_pantry(
        ingredient_ids=sorted(pantry.have | {extra}),
        excluded_staples=list(pantry.out_of),
        catalog=CATALOG,
    )
    before = rank(recipes, pantry, SearchFilters())
    after = rank(recipes, more, SearchFilters())
    matched_after = {
        match.recipe.id: {item.id for item in match.matched} for match in after.scored
    }

    for match in before.scored:
        assert {item.id for item in match.matched} <= matched_after[match.recipe.id]
    assert {m.recipe.id for m in before.all_staples} == {
        m.recipe.id for m in after.all_staples
    }


# Paging (ADR-0003 rules 7 and 9)


@settings(max_examples=150, deadline=None)
@given(
    recipe_sets(max_size=60),
    pantries(),
    st.integers(1, MAX_DECK_SIZE),
    st.data(),
)
def test_a_swipe_session_shows_every_recipe_once_in_rank_order(
    recipes: list[Recipe], pantry: Pantry, limit: int, data: st.DataObject
) -> None:
    """Hiding cards between decks, as a left swipe does, never skips or repeats."""
    service = RecipeService(
        catalog=CATALOG,
        repository=InMemoryRecipeRepository(recipes),
        keys=KEYS,
        clock=lambda: NOW,
    )
    query = SearchQuery(
        ingredient_ids=sorted(pantry.have),
        excluded_staples=sorted(pantry.out_of),
        limit=limit,
    )
    expected = rank(recipes, pantry, SearchFilters())

    scored: list[ScoredMatch] = []
    all_staples: list[AllStaplesMatch] = []
    hidden: set[UUID] = set()
    cursor = None
    for _ in range(len(recipes) + 1):
        result = asyncio.run(
            service.search(
                SearchQuery(
                    ingredient_ids=query.ingredient_ids,
                    excluded_staples=query.excluded_staples,
                    limit=limit,
                    hidden_recipe_ids=frozenset(hidden),
                    cursor=cursor,
                )
            )
        )
        deck = result.deck
        cards = len(deck.scored) + len(deck.all_staples)
        assert cards <= limit
        assert cards > 0 or not (expected.scored or expected.all_staples)
        if deck.scored:
            assert len(deck.all_staples) <= MAX_ALL_STAPLES_WITH_SCORED
        scored += deck.scored
        all_staples += deck.all_staples
        hidden |= _swiped_left(data, [*deck.scored, *deck.all_staples])
        cursor = result.next_cursor
        if cursor is None:
            break
    else:
        raise AssertionError("the session never ended")

    assert scored == list(expected.scored)
    assert all_staples == list(expected.all_staples)


def _swiped_left(
    data: st.DataObject, cards: Sequence[ScoredMatch | AllStaplesMatch]
) -> set[UUID]:
    return {card.recipe.id for card in cards if data.draw(st.booleans(), label="hide")}
