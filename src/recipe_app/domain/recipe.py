"""Recipes, built from catalog ingredients; diet is computed (ADR-0002 rule 6)."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from recipe_app.domain.catalog import Diet, Ingredient, IngredientCatalog

MAX_TOTAL_MINUTES = 24 * 60


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


class RecipeError(ValueError):
    """The recipe breaks one or more rules; `problems` lists every one."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(f"invalid recipe:\n{lines}")


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

    problems: list[str] = []

    if not isinstance(name, str) or not name.strip():
        problems.append("name must be a non-empty string")
    elif name != " ".join(name.split()):
        problems.append(f"name {name!r} has extra whitespace")

    minutes_ok = True
    for field, value in (
        ("prep_minutes", prep_minutes),
        ("cook_minutes", cook_minutes),
    ):
        # type(...) is int, not isinstance: True is an int too, and means nothing here.
        if type(value) is not int or value < 0:
            problems.append(f"{field} must be a whole number, 0 or more")
            minutes_ok = False
    if minutes_ok:
        total = prep_minutes + cook_minutes
        if total < 1:
            problems.append("total time must be at least 1 minute")
        elif total > MAX_TOTAL_MINUTES:
            problems.append(f"total time must be at most {MAX_TOTAL_MINUTES} minutes")

    if not ingredient_ids:
        problems.append("has no ingredients")
    ingredients: list[Ingredient] = []
    seen: set[str] = set()
    for ingredient_id in ingredient_ids:
        if ingredient_id in seen:
            problems.append(f"duplicate ingredient {ingredient_id!r}")
            continue
        seen.add(ingredient_id)
        found = catalog.by_id.get(ingredient_id)
        if found is None:
            problems.append(f"unknown ingredient {ingredient_id!r}")
        elif found.retired:
            problems.append(f"retired ingredient {ingredient_id!r}")
        else:
            ingredients.append(found)

    if problems:
        raise RecipeError(
            [f"recipe {name!r} ({id}): {problem}" for problem in problems]
        )

    return Recipe(
        id=id,
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredients=tuple(ingredients),
    )
