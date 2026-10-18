from uuid import UUID

import pytest

from recipe_app.domain.catalog import Diet, parse_catalog
from recipe_app.domain.recipe import build_recipe
from tests.domain.factories import catalog, category, ingredient

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
