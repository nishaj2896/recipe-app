from collections.abc import Sequence
from uuid import UUID

import pytest

from recipe_app.domain.catalog import Diet, parse_catalog
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.ranking import Ranking, SearchFilters, rank
from recipe_app.domain.recipe import Recipe, build_recipe
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="toor-dal", name="Toor dal"),
        ingredient(id="rice", name="Rice"),
        ingredient(id="peas", name="Peas", **{"class": "B"}),
        ingredient(id="spinach", name="Spinach", **{"class": "B"}),
        ingredient(id="egg", name="Egg", diet="egg"),
        ingredient(id="chicken", name="Chicken", diet="non_veg"),
        ingredient(id="tomato", name="Tomato", **{"class": "S"}, kind="fresh"),
        ingredient(id="salt", name="Salt", **{"class": "S"}, kind="pantry"),
        ingredient(
            id="ghee", name="Ghee", **{"class": "S"}, kind="pantry", diet="vegetarian"
        ),
    )
)


def recipe(
    number: int, ingredient_ids: Sequence[str], total_minutes: int = 30
) -> Recipe:
    """A recipe whose id ends in `number`, so tests can predict id order."""
    return build_recipe(
        id=UUID(int=number),
        name=f"Recipe {number}",
        prep_minutes=0,
        cook_minutes=total_minutes,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
    )


def ranked(
    recipes: Sequence[Recipe],
    have: Sequence[str] = ("potato",),
    filters: SearchFilters | None = None,
) -> Ranking:
    pantry = resolve_pantry(ingredient_ids=have, excluded_staples=(), catalog=CATALOG)
    return rank(recipes, pantry, filters or SearchFilters())


def scored_ids(ranking: Ranking) -> list[int]:
    return [match.recipe.id.int for match in ranking.scored]


def all_staples_ids(ranking: Ranking) -> list[int]:
    return [match.recipe.id.int for match in ranking.all_staples]


def test_potato_trap() -> None:
    """A curry matching 3.5 of 4.0 core weight outranks a fully matched potato."""
    single_potato = recipe(1, ["potato", "salt"])
    curry = recipe(2, ["potato", "toor-dal", "rice", "peas", "spinach", "tomato"])

    ranking = ranked([single_potato, curry], ["potato", "toor-dal", "rice", "peas"])

    assert scored_ids(ranking) == [2, 1]
    assert [match.score_int for match in ranking.scored] == [571561, 301030]


def test_equal_scores_put_the_shorter_recipe_first() -> None:
    ranking = ranked([recipe(1, ["potato"], 45), recipe(2, ["potato"], 20)])

    assert scored_ids(ranking) == [2, 1]


def test_equal_scores_and_times_put_the_lower_id_first() -> None:
    ranking = ranked([recipe(2, ["potato"]), recipe(1, ["potato"])])

    assert scored_ids(ranking) == [1, 2]


def test_all_staples_tier_is_shortest_first_then_by_id() -> None:
    recipes = [
        recipe(3, ["tomato", "salt"], 20),
        recipe(2, ["tomato"], 10),
        recipe(1, ["salt"], 20),
    ]

    assert all_staples_ids(ranked(recipes)) == [2, 1, 3]


def test_recipes_without_a_match_are_left_out() -> None:
    ranking = ranked([recipe(1, ["chicken"]), recipe(2, ["potato"])])

    assert scored_ids(ranking) == [2]
    assert all_staples_ids(ranking) == []


@pytest.mark.parametrize(
    ("diet", "expected"),
    [
        pytest.param(Diet.VEGAN, [], id="vegan"),
        pytest.param(Diet.VEGETARIAN, [], id="vegetarian"),
        pytest.param(Diet.EGG, [1], id="egg"),
        pytest.param(Diet.NON_VEG, [1, 2], id="non-veg"),
        pytest.param(None, [1, 2], id="no-diet-filter"),
    ],
)
def test_diet_filter(diet: Diet | None, expected: list[int]) -> None:
    """ADR-0002 rule 6: an egg curry is never shown to a vegetarian."""
    egg_curry = recipe(1, ["potato", "egg"])
    chicken_curry = recipe(2, ["potato", "chicken"])

    ranking = ranked([egg_curry, chicken_curry], filters=SearchFilters(diet=diet))

    assert scored_ids(ranking) == expected


def test_vegan_search_never_shows_assumed_ghee() -> None:
    """ADR-0002 rule 6: an assumed staple still sets the recipe's diet."""
    dal = recipe(1, ["toor-dal", "ghee"])

    ranking = ranked([dal], ["toor-dal"], SearchFilters(diet=Diet.VEGAN))

    assert scored_ids(ranking) == []


def test_max_total_minutes_keeps_the_boundary() -> None:
    recipes = [recipe(1, ["potato"], 30), recipe(2, ["potato"], 31)]

    ranking = ranked(recipes, filters=SearchFilters(max_total_minutes=30))

    assert scored_ids(ranking) == [1]


def test_hidden_recipes_leave_both_tiers() -> None:
    recipes = [recipe(1, ["potato"]), recipe(2, ["tomato"]), recipe(3, ["potato"])]
    filters = SearchFilters(hidden_recipe_ids=frozenset({UUID(int=1), UUID(int=2)}))

    ranking = ranked(recipes, filters=filters)

    assert scored_ids(ranking) == [3]
    assert all_staples_ids(ranking) == []


def test_input_order_does_not_change_the_result() -> None:
    recipes = [
        recipe(1, ["potato", "peas"], 40),
        recipe(2, ["potato"], 20),
        recipe(3, ["potato"], 20),
        recipe(4, ["tomato"], 15),
        recipe(5, ["salt"], 15),
    ]

    assert ranked(recipes) == ranked(list(reversed(recipes)))
