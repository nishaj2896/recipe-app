"""Recipe tags, ingredient allergens and Jain flags (ADR-0012 rules 1 to 3)."""

import re
from uuid import UUID

import pytest

from recipe_app.domain.book import RecipeBook, parse_recipe_book
from recipe_app.domain.catalog import CatalogError, Diet, Ingredient, parse_catalog
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.tags import Allergen, Course, Cuisine, Mood, Weather
from tests.domain.factories import catalog, category, ingredient
from tests.domain.test_recipe_file import (
    CATALOG,
    OTHER_ID,
    RECIPE_ID,
    parse,
    recipe_table,
)

THIRD_ID = "019a0c3e-8f02-7a1b-9c2d-3e4f5a6b7c8d"
TAGS = {
    "cuisine": "north-indian",
    "courses": ["mains"],
    "moods": ["comforting", "hearty"],
    "weather": ["rainy-day-cosy"],
    "also_known_as": ["aloo mutter"],
}


def _book(*tables: str) -> RecipeBook:
    return parse_recipe_book([("a.toml", "\n".join(tables).encode())], CATALOG)


# --- recipe tags -----------------------------------------------------------


def test_tags_are_kept() -> None:
    recipe = _book(recipe_table(**TAGS)).recipes[0]

    assert recipe.tags.cuisine is Cuisine.NORTH_INDIAN
    assert recipe.tags.courses == (Course.MAINS,)
    assert recipe.tags.moods == (Mood.COMFORTING, Mood.HEARTY)
    assert recipe.tags.weather == (Weather.RAINY_DAY_COSY,)
    assert recipe.tags.also_known_as == ("aloo mutter",)
    assert recipe.tags.pairs_with == ()


def test_optional_tags_default_to_empty() -> None:
    recipe = _book(recipe_table()).recipes[0]

    assert recipe.tags.weather == ()
    assert recipe.tags.also_known_as == ()
    assert recipe.tags.pairs_with == ()


@pytest.mark.parametrize("field", ["cuisine", "courses", "moods"])
def test_cuisine_courses_and_moods_are_required(field: str) -> None:
    problems = parse(recipe_table(**{field: None}))

    assert problems == [f"a.toml recipe #1: {field} is required"]


def test_missing_tags_show_even_without_an_id() -> None:
    problems = parse(recipe_table(id=None, cuisine=None))

    assert "a.toml recipe #1: cuisine is required" in problems, problems


def test_pairs_with_keeps_its_order() -> None:
    recipes = _book(
        recipe_table(pairs_with=[THIRD_ID, OTHER_ID]),
        recipe_table(id=OTHER_ID, name="Phulka"),
        recipe_table(id=THIRD_ID, name="Jeera rice"),
    ).recipes

    assert recipes[0].tags.pairs_with == (UUID(THIRD_ID), UUID(OTHER_ID))


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param({"cuisine": "martian"}, "unknown cuisine 'martian'", id="cuisine"),
        pytest.param({"courses": []}, "courses must have 1 to 2", id="no-course"),
        pytest.param(
            {"courses": ["mains", "sides", "soups"]},
            "courses must have 1 to 2",
            id="three-courses",
        ),
        pytest.param({"courses": ["brunch"]}, "unknown courses entry", id="course"),
        pytest.param(
            {"moods": ["spicy", "spicy"]}, "moods has duplicates", id="dup-mood"
        ),
        pytest.param(
            {"moods": ["spicy", "tangy", "sweet", "light"]},
            "moods must have 1 to 3",
            id="four-moods",
        ),
        pytest.param({"moods": "spicy"}, "moods must be a list", id="mood-string"),
        pytest.param(
            {"weather": ["need-to-cool-down", "just-pleasant", "breezy-evening", "x"]},
            "weather must have 0 to 3",
            id="four-weather",
        ),
        pytest.param({"weather": ["snowy"]}, "unknown weather entry", id="weather"),
        pytest.param({"also_known_as": ["Aloo Mutter"]}, "lower case", id="alias-case"),
        pytest.param(
            {"also_known_as": ["aloo  mutter"]}, "single-spaced", id="alias-spaces"
        ),
        pytest.param(
            {"also_known_as": ["aloo matar"]}, "the recipe's own name", id="alias-self"
        ),
        pytest.param(
            {"also_known_as": ["a", "b", "c", "d", "e", "f"]},
            "at most 5",
            id="six-aliases",
        ),
        pytest.param(
            {"also_known_as": ["a", "a"]}, "also_known_as has duplicates", id="dup"
        ),
        pytest.param(
            {"pairs_with": [RECIPE_ID]}, "names the recipe itself", id="pair-self"
        ),
        pytest.param({"pairs_with": [OTHER_ID, OTHER_ID]}, "twice", id="pair-twice"),
        pytest.param(
            {"pairs_with": [OTHER_ID.upper()]}, "lowercase UUID", id="pair-upper"
        ),
        pytest.param({"pairs_with": ["not-a-uuid"]}, "lowercase UUID", id="pair-bad"),
    ],
)
def test_bad_tags(fields: dict[str, object], expected: str) -> None:
    problems = parse(recipe_table(**fields), recipe_table(id=OTHER_ID, name="Phulka"))

    assert any(expected in problem for problem in problems), problems


def test_too_many_pairings() -> None:
    ids = [f"019a0c3e-8f1{n}-7a1b-9c2d-3e4f5a6b7c8d" for n in range(5)]

    problems = parse(recipe_table(pairs_with=ids))

    assert any("at most 4" in problem for problem in problems), problems


def test_pairs_with_must_name_a_recipe_in_the_book() -> None:
    problems = parse(recipe_table(pairs_with=[OTHER_ID]))

    assert problems == [
        f"recipe 'Aloo matar' ({RECIPE_ID}): pairs_with names unknown "
        f"recipe {OTHER_ID!r}"
    ]


def test_bad_id_still_reports_bad_tags() -> None:
    problems = parse(recipe_table(id="not-a-uuid", cuisine="martian"))

    assert any("unknown cuisine" in problem for problem in problems), problems


# --- ingredient allergens and Jain -------------------------------------------


def _one(**fields: object) -> Ingredient:
    return parse_catalog(catalog(category(), ingredient(**fields))).by_id["potato"]


def test_allergens_are_kept_in_a_fixed_order() -> None:
    item = _one(allergens=["sulphites", "gluten"])

    assert item.allergens == (Allergen.GLUTEN, Allergen.SULPHITES)


def test_no_allergens_and_jain_by_default() -> None:
    item = _one()

    assert item.allergens == ()
    assert item.jain is True


def test_jain_false_is_kept() -> None:
    assert _one(jain=False).jain is False


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        pytest.param({"allergens": ["nuts"]}, "unknown allergen 'nuts'", id="unknown"),
        pytest.param(
            {"allergens": ["dairy", "dairy"]}, "allergens has duplicates", id="dup"
        ),
        pytest.param({"allergens": "dairy"}, "allergens must be a list", id="string"),
        pytest.param({"jain": True}, "jain can only be false", id="jain-true"),
        pytest.param(
            {"jain": False, "diet": "non_veg"},
            "jain = false is only for vegan or vegetarian",
            id="jain-meat",
        ),
    ],
)
def test_bad_ingredient_flags(fields: dict[str, object], message: str) -> None:
    with pytest.raises(CatalogError, match=re.escape(message)):
        parse_catalog(catalog(category(), ingredient(**fields)))


# --- what a recipe derives from its ingredients -------------------------------

FLAGGED = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="onion", name="Onion", jain=False),
        ingredient(id="paneer", name="Paneer", diet="vegetarian", allergens=["dairy"]),
        ingredient(
            id="naan", name="Naan", diet="vegetarian", allergens=["gluten", "dairy"]
        ),
        ingredient(id="egg", name="Egg", diet="egg", allergens=["egg"]),
    )
)


def _recipe(*ingredient_ids: str) -> Recipe:
    table = recipe_table(
        ingredients=[{"id": i, "amount": 1, "unit": "cup"} for i in ingredient_ids],
        steps=[f"Cook the {i}." for i in ingredient_ids],
    )
    return parse_recipe_book([("a.toml", table.encode())], FLAGGED).recipes[0]


def test_recipe_allergens_are_the_union_in_a_fixed_order() -> None:
    recipe = _recipe("naan", "paneer", "potato")

    assert recipe.allergens == (Allergen.DAIRY, Allergen.GLUTEN)


def test_recipe_is_jain_when_every_ingredient_is() -> None:
    assert _recipe("potato", "paneer").jain is True


def test_one_non_jain_ingredient_makes_it_not_jain() -> None:
    assert _recipe("potato", "onion").jain is False


def test_an_egg_recipe_is_never_jain() -> None:
    recipe = _recipe("potato", "egg")

    assert recipe.diet is Diet.EGG
    assert recipe.jain is False


def test_an_alias_may_not_be_another_recipes_name() -> None:
    problems = parse(
        recipe_table(also_known_as=["phulka"]),
        recipe_table(id=OTHER_ID, name="Phulka"),
    )

    assert problems == [
        f"recipe 'Aloo matar' ({RECIPE_ID}): also_known_as 'phulka' is the name "
        "of 'Phulka'"
    ]


def test_an_alias_differing_only_by_punctuation_is_the_own_name() -> None:
    problems = parse(
        recipe_table(name="Peri-peri chicken", also_known_as=["peri peri chicken"])
    )

    assert any("is the name of this recipe" in problem for problem in problems), (
        problems
    )


def test_two_recipes_may_not_share_an_alias() -> None:
    problems = parse(
        recipe_table(also_known_as=["stuffed brinjal"]),
        recipe_table(
            id=OTHER_ID, name="Bharli vangi", also_known_as=["stuffed-brinjal"]
        ),
    )

    assert problems == [
        f"recipe 'Bharli vangi' ({OTHER_ID}): also_known_as 'stuffed-brinjal' is "
        "also an alias of 'Aloo matar'"
    ]


def test_one_recipe_may_not_carry_two_aliases_that_fold_together() -> None:
    problems = parse(recipe_table(also_known_as=["stuffed brinjal", "stuffed-brinjal"]))

    assert problems == [
        f"recipe 'Aloo matar' ({RECIPE_ID}): also_known_as 'stuffed-brinjal' folds "
        "to the same search key as another of its aliases"
    ]
