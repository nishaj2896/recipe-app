"""Recipe search by name (ADR-0012 rule 10)."""

from collections.abc import Sequence
from uuid import UUID

import pytest

from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.normalization import search_key
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.domain.recipe_search import (
    Criterion,
    QueryResolver,
    RecipeQuery,
    find,
    match,
    trigram_similarity,
)
from recipe_app.domain.tags import Cuisine
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(search_terms=["aloo"]),
        ingredient(id="paneer", name="Paneer", diet="vegetarian"),
        ingredient(id="peas", name="Green peas", search_terms=["matar"]),
        ingredient(id="pasta", name="Pasta", retired=True),
    )
)
RESOLVER = QueryResolver(CATALOG)


def recipe(
    number: int, name: str, ingredient_ids: Sequence[str] = ("potato",), **tags: object
) -> Recipe:
    return build_recipe(
        id=UUID(int=number),
        name=name,
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
        tags=tags,
    )


def names(recipes: Sequence[Recipe], text: str, limit: int = 20) -> list[str]:
    return [r.name for r in find(recipes, RESOLVER.resolve(text), limit, 0).recipes]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        # Postgres's own documented example for pg_trgm.
        pytest.param("word", "two words", 0.36363637, id="pg-docs"),
        pytest.param("biryani", "biryani", 1.0, id="same"),
        pytest.param("biryani", "biriyani", 0.54545456, id="misspelt"),
        pytest.param("panir bhurji", "paneer", 0.1764706, id="long-name"),
        pytest.param("abc", "xyz", 0.0, id="nothing-shared"),
        pytest.param("", "abc", 0.0, id="empty"),
    ],
)
def test_trigram_similarity_follows_pg_trgm(a: str, b: str, expected: float) -> None:
    assert trigram_similarity(a, b) == pytest.approx(expected, abs=1e-7)


def test_search_key_folds_punctuation_and_underscores() -> None:
    assert search_key("  Peri-Peri_Chicken!  ") == "peri peri chicken"


def test_the_name_start_comes_before_a_word_start_and_a_close_spelling() -> None:
    recipes = [
        recipe(1, "Matar paneer"),
        recipe(2, "Paneer tikka"),
        recipe(3, "Paneer butter masala"),
        recipe(4, "Paner"),
    ]

    assert names(recipes, "paneer") == [
        "Paneer butter masala",
        "Paneer tikka",
        "Matar paneer",
        "Paner",
    ]


def test_an_alias_matches_like_a_name_but_never_as_the_name_start() -> None:
    recipes = [
        recipe(1, "Paneer makhani", also_known_as=["butter paneer"]),
        recipe(2, "Butter chicken"),
    ]

    query = RESOLVER.resolve("butter")

    assert match(recipes[1], query) == (Criterion.NAME_STARTS, 0.0)
    assert match(recipes[0], query) == (Criterion.WORD_STARTS, 0.0)


def test_a_close_spelling_ranks_by_similarity() -> None:
    """The whole name is compared, so a long name needs more in common."""
    recipes = [
        recipe(1, "Egg biryani"),
        recipe(2, "Biryani"),
        recipe(3, "Vegetable biryani"),
    ]

    found = find(recipes, RESOLVER.resolve("biriyani"), 20, 0)

    assert [r.name for r in found.recipes] == ["Biryani", "Egg biryani"]


def test_ingredients_and_their_search_terms_find_recipes_last() -> None:
    recipes = [
        recipe(1, "Dum ki subzi", ["potato", "peas"]),
        recipe(2, "Aloo gobi"),
        recipe(3, "Shahi korma", ["paneer"]),
    ]

    assert names(recipes, "aloo") == ["Aloo gobi", "Dum ki subzi"]
    assert names(recipes, "matar") == ["Dum ki subzi"]


def test_the_cuisine_label_finds_its_recipes() -> None:
    recipes = [
        recipe(1, "Green curry", cuisine="thai"),
        recipe(2, "Fattoush", cuisine="middle-eastern"),
    ]

    assert names(recipes, "Thai") == ["Green curry"]
    assert names(recipes, "middle east") == ["Fattoush"]


def test_resolve_skips_retired_ingredients() -> None:
    query = RESOLVER.resolve("pa")

    assert query.ingredient_ids == {"paneer"}
    assert query.cuisines == frozenset()


def test_text_with_no_letters_matches_nothing() -> None:
    query = RESOLVER.resolve("--")

    assert query == RecipeQuery(
        key="", ingredient_ids=frozenset(), cuisines=frozenset()
    )
    assert find([recipe(1, "Aloo gobi")], query, 20, 0).total == 0


def test_pages_split_one_order_and_total_counts_every_match() -> None:
    recipes = [recipe(n, f"Pav bhaji {n}") for n in range(1, 6)]
    query = RESOLVER.resolve("pav")

    first = find(recipes, query, 2, 0)
    rest = find(recipes, query, 2, 2)

    assert first.total == rest.total == 5
    assert [r.id.int for r in first.recipes + rest.recipes] == [1, 2, 3, 4]


def test_cuisine_list_has_a_label_per_id() -> None:
    assert RESOLVER.resolve("south a").cuisines == {Cuisine.SOUTH_ASIAN}
