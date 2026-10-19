"""An in-memory RecipeRepository over the seed recipes (Task 1)."""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from types import MappingProxyType
from uuid import UUID

from recipe_app.domain.catalog import IngredientClass
from recipe_app.domain.matching import Pantry
from recipe_app.domain.ranking import SearchFilters, passes_filters
from recipe_app.domain.recipe import Recipe


class InMemoryRecipeRepository:
    """Indexes recipes by id and by ingredient, the way Task 2's tables will."""

    def __init__(self, recipes: Iterable[Recipe]) -> None:
        by_id: dict[UUID, Recipe] = {}
        by_ingredient: defaultdict[str, list[Recipe]] = defaultdict(list)
        all_staples: list[Recipe] = []
        for recipe in recipes:
            if recipe.id in by_id:
                raise ValueError(f"duplicate recipe id {recipe.id}")
            by_id[recipe.id] = recipe
            for ingredient in recipe.ingredients:
                by_ingredient[ingredient.id].append(recipe)
            if all(
                item.ingredient_class is IngredientClass.STAPLE
                for item in recipe.ingredients
            ):
                all_staples.append(recipe)
        self._by_id = MappingProxyType(by_id)
        self._by_ingredient = MappingProxyType(
            {key: tuple(value) for key, value in by_ingredient.items()}
        )
        self._all_staples = tuple(all_staples)

    async def get(self, recipe_id: UUID) -> Recipe | None:
        return self._by_id.get(recipe_id)

    async def candidates(
        self, pantry: Pantry, filters: SearchFilters
    ) -> Sequence[Recipe]:
        found: dict[UUID, Recipe] = {}
        for ingredient_id in sorted(pantry.have):
            for recipe in self._by_ingredient.get(ingredient_id, ()):
                found.setdefault(recipe.id, recipe)
        for recipe in self._all_staples:
            # An unticked staple makes it core, and so no longer all staples.
            if not any(item.id in pantry.out_of for item in recipe.ingredients):
                found.setdefault(recipe.id, recipe)
        return [recipe for recipe in found.values() if passes_filters(recipe, filters)]
