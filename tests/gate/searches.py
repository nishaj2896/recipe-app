"""The searches the Task 2 and Task 3 gates measure: narrow and broad pantries,
with and without filters. Shared by the gate tests and `python -m tests.gate`.
"""

from collections import Counter
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Dialect, Select

from recipe_app.domain.catalog import Diet, IngredientCatalog
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.postgres import candidates_query
from tests.gate.synthetic import synthetic_recipes

GATE_RECIPES = 50_000

# Close to the worst case the API allows: a full pantry (MAX_INGREDIENT_IDS)
# of the seed's most-used class A and B ingredients, most used first. The
# tail is a tie broken by file order, and it touches 44,571 of the 50,000
# gate recipes. Fixed, not computed, so a seed change can't silently move
# the benchmark; recompute it deliberately if the seed grows a lot.
FULL_PANTRY = [
    "egg",
    "peas",
    "curd",
    "milk",
    "potato",
    "rice",
    "paneer",
    "cream",
    "carrot",
    "basmati-rice",
    "chicken",
    "pasta",
    "bell-pepper",
    "soy-sauce",
    "kashmiri-chilli-powder",
    "dried-fenugreek-leaves",
    "toor-dal",
    "brinjal",
    "tamarind",
    "french-beans",
    "peanuts",
    "olive-oil",
    "chilli-flakes",
    "spring-onions",
    "cauliflower",
    "okra",
    "dry-mango-powder",
    "spinach",
    "cashews",
    "moong-dal",
    "masoor-dal",
    "chickpeas",
    "chole-masala",
    "kidney-beans",
    "drumsticks",
    "sambar-powder",
    "flattened-rice",
    "semolina",
    "all-purpose-flour",
    "baking-powder",
    "mint",
    "biryani-masala",
    "saffron",
    "kingfish",
    "coconut-milk",
    "coconut-oil",
    "prawns",
    "lamb-mince",
    "parsley",
    "canned-tomatoes",
]

SEARCHES: dict[str, tuple[list[str], SearchFilters]] = {
    "two rare ingredients": (["kingfish", "okra"], SearchFilters()),
    "two popular ingredients": (["potato", "peas"], SearchFilters()),
    "vegetarian, 30 minutes": (
        ["paneer", "rice"],
        SearchFilters(diet=Diet.VEGETARIAN, max_total_minutes=30),
    ),
    "ten ingredients": (
        [
            "potato",
            "peas",
            "paneer",
            "rice",
            "egg",
            "milk",
            "spinach",
            "cauliflower",
            "okra",
            "kingfish",
        ],
        SearchFilters(),
    ),
    "full pantry": (FULL_PANTRY, SearchFilters()),
}


def gate_recipes(
    catalog: IngredientCatalog, seed: Sequence[Recipe]
) -> tuple[Recipe, ...]:
    """The seed plus synthetic recipes, 50,000 in all; the seed sets which
    ingredients are popular.
    """
    usage = Counter(item.id for recipe in seed for item in recipe.ingredients)
    popular = [ingredient_id for ingredient_id, _ in usage.most_common()]
    return (
        *seed,
        *synthetic_recipes(catalog, GATE_RECIPES - len(seed), popular=popular),
    )


def search_query(name: str, catalog: IngredientCatalog) -> Select[Any]:
    ingredient_ids, filters = SEARCHES[name]
    pantry = resolve_pantry(
        ingredient_ids=ingredient_ids, excluded_staples=[], catalog=catalog
    )
    return candidates_query(pantry, filters)


def explain(
    statement: str, query: Select[Any], dialect: Dialect
) -> tuple[str, tuple[Any, ...]]:
    """`statement query` with the query's parameters, for exec_driver_sql:
    EXPLAIN takes no bound parameters of its own, so it can't wrap the query.
    """
    compiled = query.compile(dialect=dialect)
    parameters = compiled.construct_params()
    positions = compiled.positiontup or ()
    return f"{statement} {compiled}", tuple(parameters[key] for key in positions)
