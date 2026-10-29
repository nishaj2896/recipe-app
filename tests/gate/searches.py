"""The searches the Task 2 and Task 3 gates measure: narrow and broad pantries,
with and without filters. Shared by the gate tests and `python -m tests.gate`.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Dialect, Select

from recipe_app.domain.catalog import Diet, IngredientCatalog
from recipe_app.domain.deck import MAX_DECK_SIZE
from recipe_app.domain.matching import Pantry, resolve_pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.scoring import score_triangle
from recipe_app.infra.postgres import all_staples_query, scored_query
from tests.gate.synthetic import synthetic_recipes

GATE_RECIPES = 50_000
# What a pod sizes for the gate seed: twice its largest reachable core_q, 32.
GATE_SCORES = score_triangle(64)

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


@dataclass(frozen=True, slots=True)
class GateSearch:
    ingredient_ids: list[str]
    filters: SearchFilters = field(default_factory=SearchFilters)
    excluded_staples: list[str] = field(default_factory=list)

    def pantry(self, catalog: IngredientCatalog) -> Pantry:
        return resolve_pantry(
            ingredient_ids=self.ingredient_ids,
            excluded_staples=self.excluded_staples,
            catalog=catalog,
        )


SEARCHES: dict[str, GateSearch] = {
    "two rare ingredients": GateSearch(["kingfish", "okra"]),
    "two popular ingredients": GateSearch(["potato", "peas"]),
    "vegetarian, 30 minutes": GateSearch(
        ["paneer", "rice"], SearchFilters(diet=Diet.VEGETARIAN, max_total_minutes=30)
    ),
    "ten ingredients": GateSearch(
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
        ]
    ),
    "full pantry": GateSearch(FULL_PANTRY),
    # Unticked staples are in most recipes, so core_q costs one lookup per
    # candidate: the most work a search can ask for (ADR-0007 rule 3).
    "full pantry, out of salt and turmeric": GateSearch(
        FULL_PANTRY, excluded_staples=["salt", "turmeric"]
    ),
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


def search_queries(name: str, catalog: IngredientCatalog) -> dict[str, Select[Any]]:
    """The search's two queries, as the first deck runs them."""
    search = SEARCHES[name]
    pantry = search.pantry(catalog)
    # One deck plus the one that says whether another deck exists.
    limit = MAX_DECK_SIZE + 1
    return {
        "scored": scored_query(pantry, search.filters, None, limit, GATE_SCORES),
        "all staples": all_staples_query(pantry, search.filters, None, limit),
    }


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
