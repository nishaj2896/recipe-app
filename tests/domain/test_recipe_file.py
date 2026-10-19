import json
from collections import Counter

import pytest

from recipe_app.domain.catalog import Diet, IngredientClass, parse_catalog
from recipe_app.domain.recipe import RecipeError, parse_recipes
from recipe_app.infra.data import DATA_DIR, RECIPES_FILE, load_catalog
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="peas", name="Peas", **{"class": "B"}),
        ingredient(id="leek", name="Leek", **{"class": "B"}, retired=True),
    )
)
RECIPE_ID = "019a0c3e-8f00-7a1b-9c2d-3e4f5a6b7c8d"
OTHER_ID = "019a0c3e-8f01-7a1b-9c2d-3e4f5a6b7c8d"


def recipe_table(**fields: object) -> str:
    """A valid [[recipe]] table. Override fields; None drops one."""
    row: dict[str, object] = {
        "id": RECIPE_ID,
        "name": "Aloo matar",
        "prep_minutes": 10,
        "cook_minutes": 20,
        "ingredients": ["potato", "peas"],
    } | fields
    lines = [
        f"{key} = {json.dumps(value)}"
        for key, value in row.items()
        if value is not None
    ]
    return "[[recipe]]\n" + "\n".join(lines) + "\n"


def parse(*tables: str) -> list[str]:
    """The problems parse_recipes reports, or [] if the file is valid."""
    try:
        parse_recipes("\n".join(tables).encode(), CATALOG)
    except RecipeError as error:
        return error.problems
    return []


def test_valid_file_keeps_file_order() -> None:
    raw = (recipe_table() + recipe_table(id=OTHER_ID, name="Peas pulao")).encode()

    recipes = parse_recipes(raw, CATALOG)

    assert [str(recipe.id) for recipe in recipes] == [RECIPE_ID, OTHER_ID]
    assert [item.id for item in recipes[0].ingredients] == ["potato", "peas"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(b"", "the recipe file is empty", id="empty"),
        pytest.param(b"  \n", "the recipe file is empty", id="blank"),
        pytest.param(b"[[recipe]\n", "not valid TOML", id="bad-toml"),
        pytest.param(b"title = 'x'\n", "unknown top-level key 'title'", id="extra-key"),
    ],
)
def test_bad_file(raw: bytes, expected: str) -> None:
    with pytest.raises(RecipeError) as caught:
        parse_recipes(raw, CATALOG)

    assert any(expected in problem for problem in caught.value.problems)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param({"serves": 2}, "unknown field 'serves'", id="unknown-field"),
        pytest.param({"id": None}, "id must be a lowercase UUID", id="no-id"),
        pytest.param({"id": "not-a-uuid"}, "id must be a lowercase UUID", id="bad-id"),
        pytest.param(
            {"id": RECIPE_ID.upper()}, "id must be a lowercase UUID", id="upper-id"
        ),
        pytest.param(
            {"id": RECIPE_ID.replace("-", "")},
            "id must be a lowercase UUID",
            id="unhyphenated-id",
        ),
        pytest.param({"ingredients": "potato"}, "must be a list", id="ingredients-str"),
        pytest.param({"ingredients": ["okra"]}, "unknown ingredient", id="unknown"),
        pytest.param({"ingredients": ["leek"]}, "retired ingredient", id="retired"),
        pytest.param({"prep_minutes": "10"}, "prep_minutes must be", id="minutes-str"),
        pytest.param({"name": None}, "name must be", id="no-name"),
    ],
)
def test_bad_recipe(fields: dict[str, object], expected: str) -> None:
    problems = parse(recipe_table(**fields))

    assert any(expected in problem for problem in problems), problems


def test_duplicate_id() -> None:
    problems = parse(recipe_table(), recipe_table(name="Peas pulao"))

    assert problems == [f"duplicate recipe id {RECIPE_ID!r}"]


def test_duplicate_name_after_normalization() -> None:
    problems = parse(recipe_table(), recipe_table(id=OTHER_ID, name="ALOO MATAR"))

    assert problems == ["duplicate recipe name 'aloo matar'"]


def test_reports_every_problem_at_once() -> None:
    problems = parse(
        recipe_table(serves=2),
        recipe_table(id=OTHER_ID, name="Peas pulao", ingredients=["okra"]),
    )

    assert len(problems) == 2


# The checked-in seed file: the same checks as app startup (ADR-0002 rule 7).

SEED = parse_recipes((DATA_DIR / RECIPES_FILE).read_bytes(), load_catalog())


def test_seed_file_loads() -> None:
    assert len(SEED) >= 40


def test_seed_covers_every_diet() -> None:
    assert set(Counter(recipe.diet for recipe in SEED)) == set(Diet)


def test_seed_has_all_staples_recipes() -> None:
    """The all-staples tier needs real cards for the demo and the gate."""
    all_staples = [
        recipe
        for recipe in SEED
        if all(i.ingredient_class is IngredientClass.STAPLE for i in recipe.ingredients)
    ]

    assert len(all_staples) >= 2
