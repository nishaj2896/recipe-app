"""Gate fixtures: the real catalog, plus recipes named after the gate's examples."""

from collections.abc import AsyncIterator, Sequence
from itertools import cycle
from uuid import UUID

import pytest
from httpx import AsyncClient

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.recipe import Recipe, build_recipe
from tests.apps import AppFactory, client_for

# Fixed ids, so assertions can name recipes and the id tie-break is predictable.
POTATO_CURRY = UUID(int=1)
TOMATO_SOUP = UUID(int=2)
KHEER = UUID(int=3)
EGG_CURRY = UUID(int=4)
PANEER_PEAS = UUID(int=5)
CHANA = UUID(int=6)
SLOW_POTATO = UUID(int=7)
CHICKEN_CURRY = UUID(int=8)
PEANUT_EGG_SALAD = UUID(int=9)
QUICK_PEAS_RICE = UUID(int=10)
SLOW_PEAS_RICE = UUID(int=11)
GHEE_DAL = UUID(int=12)
OKRA_FRY = UUID(int=13)


def make(
    catalog: IngredientCatalog,
    recipe_id: UUID,
    name: str,
    ingredients: Sequence[str],
    prep: int = 10,
    cook: int = 20,
) -> Recipe:
    return build_recipe(
        id=recipe_id,
        name=name,
        prep_minutes=prep,
        cook_minutes=cook,
        ingredient_ids=ingredients,
        catalog=catalog,
    )


@pytest.fixture(scope="session")
def gate_recipes(real_catalog: IngredientCatalog) -> tuple[Recipe, ...]:
    c = real_catalog
    staples = ["tomato", "onion", "turmeric", "salt", "ghee"]
    return (
        make(c, POTATO_CURRY, "Potato curry", ["potato", "peas", *staples], 10, 20),
        make(
            c,
            TOMATO_SOUP,
            "Tomato soup",
            ["tomato", "onion", "garlic", "butter", "salt"],
        ),
        make(c, KHEER, "Kheer", ["rice", "milk", "sugar"], 5, 40),
        make(c, EGG_CURRY, "Egg curry", ["egg", "onion", "tomato", "oil", "salt"]),
        make(c, PANEER_PEAS, "Matar paneer", ["paneer", "peas", "oil", "salt"]),
        make(c, CHANA, "Chana masala", ["chickpeas", "onion", "tomato", "oil", "salt"]),
        make(c, SLOW_POTATO, "Dum aloo", ["potato", "curd", "oil", "salt"], 10, 25),
        make(c, CHICKEN_CURRY, "Chicken curry", ["chicken", "onion", "oil", "salt"]),
        make(
            c, PEANUT_EGG_SALAD, "Peanut egg salad", ["egg", "peanuts", "oil", "salt"]
        ),
        make(c, QUICK_PEAS_RICE, "Quick peas rice", ["peas", "rice", "salt"], 5, 15),
        make(c, SLOW_PEAS_RICE, "Slow peas rice", ["peas", "rice", "salt"], 10, 30),
        make(c, GHEE_DAL, "Ghee dal", ["toor-dal", "ghee", "salt"], 5, 25),
        make(c, OKRA_FRY, "Okra fry", ["okra", "oil", "salt"], 5, 15),
    )


def bulk(
    catalog: IngredientCatalog, scored: int, all_staples: int
) -> tuple[Recipe, ...]:
    """Many recipes with few distinct scores and times, so ties are common."""
    shapes = cycle([["potato"], ["potato", "peas"], ["potato", "rice"]])
    times = cycle([20, 30, 45])
    made = [
        make(catalog, UUID(int=1000 + n), f"Scored {n}", next(shapes), 0, next(times))
        for n in range(scored)
    ]
    made += [
        make(
            catalog,
            UUID(int=5000 + n),
            f"Staples {n}",
            ["tomato", "salt"],
            0,
            next(times),
        )
        for n in range(all_staples)
    ]
    return tuple(made)


@pytest.fixture
async def gate(
    make_app: AppFactory, gate_recipes: tuple[Recipe, ...]
) -> AsyncIterator[AsyncClient]:
    async with client_for(make_app(recipes=gate_recipes)) as client:
        yield client
