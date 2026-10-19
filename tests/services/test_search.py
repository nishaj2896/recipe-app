import asyncio
from dataclasses import replace
from uuid import UUID

import pytest

from recipe_app.domain.catalog import Diet, IngredientCatalog, parse_catalog
from recipe_app.domain.cursor import (
    ExpiredCursorError,
    InvalidCursorError,
    SigningKeys,
)
from recipe_app.domain.deck import Deck
from recipe_app.domain.matching import IgnoredReason, PantryError, resolve_pantry
from recipe_app.domain.ranking import SearchFilters, rank
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.services.search import RecipeService, SearchQuery, SearchResult
from tests.domain.factories import DATA_DIR, catalog, category, ingredient

KEYS = SigningKeys(active_kid="a", keys={"a": b"a" * 32})
NOW = 1_800_000_000
MAX_PAGES = 100

CATALOG = load_catalog(DATA_DIR)
SEED = load_recipes(CATALOG, DATA_DIR)
# Common enough that most seed recipes are scored, so walks span several decks.
BROAD = ["potato", "peas", "paneer", "rice", "basmati-rice", "egg", "chicken"]


def service(
    recipes: tuple[Recipe, ...] = SEED,
    *,
    clock_offset: int = 0,
    keys: SigningKeys = KEYS,
    catalog_: IngredientCatalog = CATALOG,
) -> RecipeService:
    return RecipeService(
        catalog=catalog_,
        repository=InMemoryRecipeRepository(recipes),
        keys=keys,
        clock=lambda: NOW + clock_offset,
    )


def search(svc: RecipeService, query: SearchQuery) -> SearchResult:
    return asyncio.run(svc.search(query))


def card_ids(deck: Deck) -> list[UUID]:
    return [m.recipe.id for m in deck.scored] + [m.recipe.id for m in deck.all_staples]


def walk(svc: RecipeService, query: SearchQuery) -> list[SearchResult]:
    """Follow next_cursor until it is null; fail instead of looping forever."""
    pages: list[SearchResult] = []
    for _ in range(MAX_PAGES):
        page = search(svc, query)
        pages.append(page)
        if page.next_cursor is None:
            return pages
        query = replace(query, cursor=page.next_cursor)
    raise AssertionError(f"next_cursor still set after {MAX_PAGES} pages")


def test_walk_returns_every_eligible_recipe_once() -> None:
    query = SearchQuery(ingredient_ids=BROAD, limit=7)

    pages = walk(service(), query)

    shown = [i for page in pages for i in card_ids(page.deck)]
    assert len(pages) > 2
    assert all(card_ids(page.deck) for page in pages)
    assert all(len(card_ids(page.deck)) <= 7 for page in pages)
    assert len(shown) == len(set(shown))
    pantry = resolve_pantry(ingredient_ids=BROAD, excluded_staples=[], catalog=CATALOG)
    full = rank(SEED, pantry, SearchFilters())
    # Each tier comes out in exact rank order across the pages.
    assert [m.recipe.id for page in pages for m in page.deck.scored] == [
        m.recipe.id for m in full.scored
    ]
    assert [m.recipe.id for page in pages for m in page.deck.all_staples] == [
        m.recipe.id for m in full.all_staples
    ]


def recipes_named(*names: str) -> tuple[Recipe, ...]:
    return tuple(recipe for recipe in SEED if recipe.name in names)


def test_last_page_has_no_cursor() -> None:
    """No cursor that leads to an empty deck: the app would show a blank card."""
    pool = recipes_named("Kerala fish curry", "Nimbu pani")
    query = SearchQuery(ingredient_ids=["kingfish"], limit=1)

    first = search(service(pool), query)
    second = search(service(pool), replace(query, cursor=first.next_cursor))

    assert [m.recipe.name for m in first.deck.scored] == ["Kerala fish curry"]
    assert first.next_cursor is not None
    assert [m.recipe.name for m in second.deck.all_staples] == ["Nimbu pani"]
    assert second.next_cursor is None


def test_no_match_is_an_empty_deck_not_an_error() -> None:
    pool = recipes_named("Kerala fish curry")

    page = search(service(pool), SearchQuery(ingredient_ids=["potato"]))

    assert page.deck == Deck(scored=(), all_staples=())
    assert page.next_cursor is None


def test_same_request_twice_gives_the_same_result() -> None:
    query = SearchQuery(ingredient_ids=BROAD, excluded_staples=["turmeric"])

    assert search(service(), query) == search(service(), query)


def test_hidden_recipes_never_show_even_when_hidden_mid_walk() -> None:
    query = SearchQuery(ingredient_ids=BROAD, limit=5)
    first = search(service(), query)
    second_before = search(service(), replace(query, cursor=first.next_cursor))
    hide = frozenset({card_ids(first.deck)[0], card_ids(second_before.deck)[1]})

    second = search(
        service(),
        replace(query, cursor=first.next_cursor, hidden_recipe_ids=hide),
    )

    assert not hide & set(card_ids(second.deck))
    assert set(card_ids(second_before.deck)) - hide <= set(card_ids(second.deck))


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"diet": Diet.VEGAN}, id="diet"),
        pytest.param({"max_total_minutes": 30}, id="time"),
        pytest.param({"ingredient_ids": ["potato"]}, id="ingredients"),
        pytest.param({"excluded_staples": ["salt"]}, id="excluded"),
    ],
)
def test_cursor_reused_with_other_filters_is_invalid(change: dict[str, object]) -> None:
    query = SearchQuery(ingredient_ids=BROAD, limit=5)
    cursor = search(service(), query).next_cursor

    with pytest.raises(InvalidCursorError):
        search(service(), replace(query, cursor=cursor, **change))  # type: ignore[arg-type]


def test_cursor_survives_a_different_limit() -> None:
    query = SearchQuery(ingredient_ids=BROAD, limit=5)
    first = search(service(), query)
    second_small = search(service(), replace(query, cursor=first.next_cursor))

    second_big = search(service(), replace(query, cursor=first.next_cursor, limit=20))

    assert not set(card_ids(first.deck)) & set(card_ids(second_big.deck))
    assert second_big.deck.scored[0] == second_small.deck.scored[0]


@pytest.mark.parametrize("limit", [0, 21])
def test_limit_out_of_range_fails_before_any_work(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        SearchQuery(ingredient_ids=["potato"], limit=limit)


def test_key_rotation_keeps_old_cursors_until_the_old_key_is_removed() -> None:
    query = SearchQuery(ingredient_ids=BROAD, limit=5)
    cursor = search(service(), query).next_cursor
    rotated = SigningKeys(active_kid="b", keys={"a": b"a" * 32, "b": b"b" * 32})
    removed = SigningKeys(active_kid="b", keys={"b": b"b" * 32})

    page = search(service(keys=rotated), replace(query, cursor=cursor))

    assert page.deck.scored
    assert page.next_cursor is not None
    assert search(service(keys=rotated), replace(query, cursor=page.next_cursor))
    with pytest.raises(ExpiredCursorError):
        search(service(keys=removed), replace(query, cursor=cursor))


def test_cursor_after_a_catalog_change_is_expired() -> None:
    query = SearchQuery(ingredient_ids=["potato"], limit=1)
    cursor = search(service(), query).next_cursor
    other = parse_catalog(catalog(category(), ingredient()))
    potato = build_recipe(
        id=UUID(int=1),
        name="Boiled potato",
        prep_minutes=0,
        cook_minutes=20,
        ingredient_ids=["potato"],
        catalog=other,
    )

    with pytest.raises(ExpiredCursorError):
        search(service((potato,), catalog_=other), replace(query, cursor=cursor))


def test_cursor_older_than_a_day_is_expired() -> None:
    query = SearchQuery(ingredient_ids=BROAD, limit=5)
    cursor = search(service(), query).next_cursor

    with pytest.raises(ExpiredCursorError):
        search(service(clock_offset=86_401), replace(query, cursor=cursor))


def test_bad_cursor_is_checked_before_the_pantry() -> None:
    with pytest.raises(InvalidCursorError):
        search(service(), SearchQuery(ingredient_ids=["no-such-id"], cursor="junk"))


def test_unknown_ingredient_is_a_pantry_error() -> None:
    with pytest.raises(PantryError, match="unknown ingredient 'no-such-id'"):
        search(service(), SearchQuery(ingredient_ids=["potato", "no-such-id"]))


def test_ignored_ids_are_reported() -> None:
    page = search(
        service(),
        SearchQuery(ingredient_ids=["potato", "salt"], excluded_staples=["paneer"]),
    )

    assert [(i.ingredient.id, i.reason) for i in page.ignored] == [
        ("salt", IgnoredReason.NOW_STAPLE),
        ("paneer", IgnoredReason.NOT_STAPLE),
    ]


def test_get_recipe() -> None:
    assert asyncio.run(service().get_recipe(SEED[0].id)) == SEED[0]
    assert asyncio.run(service().get_recipe(UUID(int=0))) is None
