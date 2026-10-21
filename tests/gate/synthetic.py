"""Synthetic recipes at production size, for the Task 2 gate (query plans).

Deterministic for a given seed, so a plan in the gate report can be
reproduced. Shaped like the seed file: mostly staples, a few core
ingredients each, and a long tail of rarely used ingredients, because the
planner's choices depend on how many recipes each ingredient matches.
"""

import random
from collections.abc import Sequence
from uuid import UUID

from recipe_app.domain.catalog import IngredientCatalog, IngredientClass
from recipe_app.domain.recipe import Recipe, build_recipe

# How many core (class A and B) ingredients a recipe has, and how often.
CORE_COUNTS = (0, 1, 2, 3, 4, 5, 6)
CORE_WEIGHTS = (2, 10, 25, 28, 18, 11, 6)
STAPLE_COUNTS = range(3, 9)
PREP_MINUTES = (0, 5, 10, 15, 20, 30, 45, 480)
PREP_WEIGHTS = (10, 25, 25, 15, 10, 8, 5, 2)


def synthetic_recipes(
    catalog: IngredientCatalog,
    count: int,
    *,
    popular: Sequence[str] = (),
    seed: int = 2,
) -> tuple[Recipe, ...]:
    """`count` valid recipes over the catalog's live ingredients.

    Popularity follows Zipf's law, most popular first: `popular` in its
    order, then the rest shuffled. At 50,000 recipes the top ingredient is
    in about a third of them and the median one in under a hundred. That
    skew is what makes some searches cheap and others expensive.
    """
    rng = random.Random(seed)  # noqa: S311 - test data, not security
    live = [item for item in catalog.by_id.values() if not item.retired]
    core = sorted(
        item.id for item in live if item.ingredient_class is not IngredientClass.STAPLE
    )
    staples = sorted(
        item.id for item in live if item.ingredient_class is IngredientClass.STAPLE
    )
    rng.shuffle(core)
    first = [item for item in dict.fromkeys(popular) if item in core]
    core = first + [item for item in core if item not in first]
    rng.shuffle(staples)
    core_weights = [1 / rank for rank in range(1, len(core) + 1)]
    staple_weights = [1 / rank**0.7 for rank in range(1, len(staples) + 1)]

    recipes = []
    for number in range(count):
        wanted = rng.choices(CORE_COUNTS, CORE_WEIGHTS)[0]
        ingredient_ids = _distinct(rng, core, core_weights, wanted)
        ingredient_ids += _distinct(
            rng, staples, staple_weights, rng.choice(STAPLE_COUNTS)
        )
        recipes.append(
            build_recipe(
                id=UUID(int=rng.getrandbits(128), version=4),
                name=f"Synthetic recipe {number + 1}",
                prep_minutes=rng.choices(PREP_MINUTES, PREP_WEIGHTS)[0],
                cook_minutes=max(1, round(rng.lognormvariate(3.2, 0.6))),
                ingredient_ids=ingredient_ids,
                catalog=catalog,
            )
        )
    return tuple(recipes)


def _distinct(
    rng: random.Random, population: list[str], weights: list[float], k: int
) -> list[str]:
    chosen: dict[str, None] = {}
    while len(chosen) < k:
        chosen[rng.choices(population, weights)[0]] = None
    return list(chosen)
