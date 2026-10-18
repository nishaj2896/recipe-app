import re
from dataclasses import FrozenInstanceError
from typing import Any
from uuid import UUID

import pytest

from recipe_app.domain.catalog import Diet, parse_catalog
from recipe_app.domain.recipe import (
    MAX_TOTAL_MINUTES,
    Recipe,
    RecipeError,
    build_recipe,
)
from tests.domain.factories import DATA_FILE, catalog, category, ingredient

RECIPE_ID = UUID("6f1c2b9e-3d4a-4c5e-9f70-1a2b3c4d5e6f")

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="toor-dal", name="Toor dal"),
        ingredient(
            id="ghee", name="Ghee", **{"class": "S"}, kind="pantry", diet="vegetarian"
        ),
        ingredient(id="paneer", name="Paneer", diet="vegetarian"),
        ingredient(id="egg", name="Egg", diet="egg"),
        ingredient(id="chicken", name="Chicken", diet="non_veg"),
        ingredient(id="leek", name="Leek", **{"class": "B"}, retired=True),
    )
)


@pytest.mark.parametrize(
    ("ingredient_ids", "expected"),
    [
        pytest.param(["potato", "toor-dal"], Diet.VEGAN, id="all-vegan"),
        pytest.param(["toor-dal", "ghee"], Diet.VEGETARIAN, id="assumed-ghee-counts"),
        pytest.param(["potato", "egg"], Diet.EGG, id="egg-beats-vegan"),
        pytest.param(["paneer", "chicken"], Diet.NON_VEG, id="chicken-beats-paneer"),
    ],
)
def test_recipe_diet(ingredient_ids: list[str], expected: Diet) -> None:
    recipe = build_recipe(
        id=RECIPE_ID,
        name="Test recipe",
        prep_minutes=10,
        cook_minutes=20,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
    )

    assert recipe.diet is expected


def build(
    *,
    name: str = "Aloo matar",
    prep_minutes: int = 10,
    cook_minutes: int = 20,
    ingredient_ids: tuple[str, ...] = ("potato",),
) -> Recipe:
    """A valid recipe from CATALOG. Override one argument to break one rule."""
    return build_recipe(
        id=RECIPE_ID,
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
    )


def test_total_minutes_is_prep_plus_cook() -> None:
    assert build(prep_minutes=15, cook_minutes=25).total_minutes == 40


@pytest.mark.parametrize(
    ("prep_minutes", "cook_minutes"),
    [
        pytest.param(0, 20, id="no-prep-boiled-eggs"),
        pytest.param(10, 0, id="no-cook-raita"),
        pytest.param(1440, 0, id="exactly-24-hours"),
    ],
)
def test_accepts_edge_times(prep_minutes: int, cook_minutes: int) -> None:
    recipe = build(prep_minutes=prep_minutes, cook_minutes=cook_minutes)

    assert recipe.total_minutes == prep_minutes + cook_minutes


def test_keeps_ingredient_order() -> None:
    recipe = build(ingredient_ids=("toor-dal", "ghee", "potato"))

    assert [item.id for item in recipe.ingredients] == ["toor-dal", "ghee", "potato"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        pytest.param(
            {"ingredient_ids": ("potatoe",)},
            "unknown ingredient 'potatoe'",
            id="unknown-id",
        ),
        pytest.param(
            {"ingredient_ids": ("potato", "leek")},
            "retired ingredient 'leek'",
            id="retired-id",
        ),
        pytest.param(
            {"ingredient_ids": ("potato", "potato")},
            "duplicate ingredient 'potato'",
            id="duplicate-id",
        ),
        pytest.param({"ingredient_ids": ()}, "has no ingredients", id="no-ingredients"),
        pytest.param({"name": ""}, "name must be a non-empty string", id="empty-name"),
        pytest.param(
            {"name": "Aloo  matar"},
            "name 'Aloo  matar' has extra whitespace",
            id="name-whitespace",
        ),
        pytest.param(
            {"prep_minutes": -5},
            "prep_minutes must be a whole number, 0 or more",
            id="negative-prep",
        ),
        pytest.param(
            {"cook_minutes": -1},
            "cook_minutes must be a whole number, 0 or more",
            id="negative-cook",
        ),
        pytest.param(
            {"prep_minutes": True},
            "prep_minutes must be a whole number, 0 or more",
            id="bool-prep",
        ),
        pytest.param(
            {"prep_minutes": 0, "cook_minutes": 0},
            "total time must be at least 1 minute",
            id="zero-total",
        ),
        pytest.param(
            {"prep_minutes": 1000, "cook_minutes": 441},
            f"total time must be at most {MAX_TOTAL_MINUTES} minutes",
            id="over-24-hours",
        ),
    ],
)
def test_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(RecipeError, match=re.escape(message)):
        build(**overrides)


def test_problem_names_the_recipe() -> None:
    with pytest.raises(
        RecipeError, match=re.escape(f"recipe 'Aloo matar' ({RECIPE_ID})")
    ):
        build(ingredient_ids=("potatoe",))


def test_reports_every_problem_at_once() -> None:
    with pytest.raises(RecipeError) as caught:
        build(prep_minutes=-5, ingredient_ids=("potatoe", "leek"))

    assert len(caught.value.problems) == 3


def test_recipe_is_read_only() -> None:
    recipe = build()

    with pytest.raises(FrozenInstanceError):
        recipe.name = "Changed"  # type: ignore[misc]


def test_potato_recipe_from_real_catalog_is_vegetarian() -> None:
    real_catalog = parse_catalog(DATA_FILE.read_bytes())

    recipe = build_recipe(
        id=RECIPE_ID,
        name="Aloo matar",
        prep_minutes=10,
        cook_minutes=25,
        ingredient_ids=[
            "potato",
            "peas",
            "tomato",
            "onion",
            "turmeric",
            "salt",
            "ghee",
        ],
        catalog=real_catalog,
    )

    assert recipe.diet is Diet.VEGETARIAN
