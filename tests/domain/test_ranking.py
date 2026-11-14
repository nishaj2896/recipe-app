from collections.abc import Sequence
from uuid import UUID

import pytest

from recipe_app.domain.catalog import Diet, parse_catalog
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.ranking import Ranking, SearchFilters, rank
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.domain.tags import Allergen, Course, Mood, Weather
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
        ingredient(id="peanuts", name="Peanuts", allergens=["peanuts"]),
        ingredient(id="onion", name="Onion", **{"class": "B"}, jain=False),
    )
)


def recipe(
    number: int,
    ingredient_ids: Sequence[str],
    total_minutes: int = 30,
    **tags: object,
) -> Recipe:
    """A recipe whose id ends in `number`, so tests can predict id order."""
    return build_recipe(
        id=UUID(int=number),
        name=f"Recipe {number}",
        prep_minutes=0,
        cook_minutes=total_minutes,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
        tags=tags,
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


def test_min_total_minutes_keeps_the_boundary() -> None:
    recipes = [recipe(1, ["potato"], 60), recipe(2, ["potato"], 61)]

    ranking = ranked(recipes, filters=SearchFilters(min_total_minutes=61))

    assert scored_ids(ranking) == [2]


def test_jain_leaves_out_onion_and_meat() -> None:
    """ADR-0012 rule 4: Jain is vegetarian or vegan with no onion."""
    recipes = [
        recipe(1, ["potato"]),
        recipe(2, ["potato", "onion"]),
        recipe(3, ["potato", "chicken"]),
    ]

    ranking = ranked(recipes, filters=SearchFilters(jain=True))

    assert scored_ids(ranking) == [1]


def test_an_avoided_allergen_removes_the_recipe_from_both_tiers() -> None:
    recipes = [recipe(1, ["potato", "peanuts"]), recipe(2, ["potato"])]
    filters = SearchFilters(avoid_allergens=frozenset({Allergen.PEANUTS}))

    assert scored_ids(ranked(recipes, filters=filters)) == [2]


def test_an_avoided_ingredient_counts_even_as_an_assumed_staple() -> None:
    recipes = [recipe(1, ["potato", "tomato"]), recipe(2, ["salt"])]
    filters = SearchFilters(avoid_ingredient_ids=frozenset({"tomato", "salt"}))

    ranking = ranked(recipes, filters=filters)

    assert scored_ids(ranking) == []
    assert all_staples_ids(ranking) == []


def test_courses_and_moods_keep_recipes_with_any_of_them() -> None:
    recipes = [
        recipe(1, ["potato"], courses=["mains"], moods=["spicy"]),
        recipe(2, ["potato"], courses=["sides"], moods=["tangy"]),
        recipe(3, ["potato"], courses=["mains"], moods=["creamy"]),
        recipe(4, ["potato"]),
    ]
    filters = SearchFilters(
        courses=frozenset({Course.MAINS, Course.SIDES}),
        moods=frozenset({Mood.SPICY, Mood.TANGY}),
    )

    assert scored_ids(ranked(recipes, filters=filters)) == [1, 2]


def test_weather_moves_recipes_forward_and_never_removes_one() -> None:
    recipes = [
        recipe(1, ["potato"]),
        recipe(2, ["potato"], weather=["rainy-day-cosy"]),
        recipe(3, ["tomato"]),
        recipe(4, ["tomato"], weather=["warming", "rainy-day-cosy"]),
    ]
    filters = SearchFilters(weather=frozenset({Weather.RAINY_DAY_COSY}))

    ranking = ranked(recipes, filters=filters)

    assert scored_ids(ranking) == [2, 1]
    assert all_staples_ids(ranking) == [4, 3]
    assert [m.weather_fit for m in ranking.scored] == [True, False]


def test_fit_comes_before_pantry_match() -> None:
    """ADR-0012 rule 6: spicy and tangy beats only spicy, even with a lower
    score; with the same fit, the pantry match decides.
    """
    both = recipe(1, ["potato", "rice", "peas"], moods=["spicy", "tangy"])
    spicy = recipe(2, ["potato"], moods=["spicy"])
    spicy_rainy = recipe(3, ["potato", "rice"], moods=["spicy"], weather=["warming"])
    spicy_full = recipe(4, ["potato", "rice"], moods=["spicy"])
    filters = SearchFilters(
        moods=frozenset({Mood.SPICY, Mood.TANGY}),
        weather=frozenset({Weather.WARMING}),
    )

    ranking = ranked([spicy, spicy_full, spicy_rainy, both], ["potato"], filters)

    assert scored_ids(ranking) == [3, 1, 2, 4]
    assert [m.fit for m in ranking.scored] == [2, 2, 1, 1]


def test_with_nothing_picked_every_fit_is_zero() -> None:
    recipes = [recipe(1, ["potato"], moods=["spicy"], weather=["warming"])]

    [match] = ranked(recipes).scored

    assert (match.fit, match.weather_fit) == (0, False)
