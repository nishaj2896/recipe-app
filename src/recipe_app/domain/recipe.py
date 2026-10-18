"""Recipes, built from catalog ingredients; diet is computed (ADR-0002 rule 6)."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from recipe_app.domain.catalog import Diet, Ingredient, IngredientCatalog


@dataclass(frozen=True, slots=True)
class Recipe:
    """A recipe made only of real catalog ingredients; build it with build_recipe.

    Soaking, fermenting and marinating count as prep time.
    """

    id: UUID
    name: str
    prep_minutes: int
    cook_minutes: int
    ingredients: tuple[Ingredient, ...]

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes

    @property
    def diet(self) -> Diet:
        """The highest diet tag across every ingredient, assumed staples included."""
        return max(
            (ingredient.diet for ingredient in self.ingredients),
            key=lambda diet: diet.rank,
        )


def build_recipe(
    *,
    id: UUID,
    name: str,
    prep_minutes: int,
    cook_minutes: int,
    ingredient_ids: Sequence[str],
    catalog: IngredientCatalog,
) -> Recipe:
    """Resolve every ingredient id against the catalog and return the recipe."""
    return Recipe(
        id=id,
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredients=tuple(catalog.by_id[item] for item in ingredient_ids),
    )
