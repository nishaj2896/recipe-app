"""Recipes, built from catalog ingredients; diet is computed (ADR-0002 rule 6)."""

import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from recipe_app.domain.catalog import (
    Diet,
    Ingredient,
    IngredientCatalog,
    IngredientClass,
)
from recipe_app.domain.normalization import normalize

RECIPE_FIELDS = frozenset({"id", "name", "prep_minutes", "cook_minutes", "ingredients"})

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

    @property
    def all_staples(self) -> bool:
        """Every ingredient is a staple, so any pantry can cook it (ADR-0003)."""
        return all(
            ingredient.ingredient_class is IngredientClass.STAPLE
            for ingredient in self.ingredients
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
    """Resolve every ingredient id against the catalog and check every rule.

    Collects every problem before raising, like parse_catalog, so a seed file
    with several mistakes shows them all in one run.
    """
    problems, ingredients = _check_recipe(
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredient_ids=ingredient_ids,
        catalog=catalog,
    )
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


def _check_recipe(
    *,
    name: str,
    prep_minutes: int,
    cook_minutes: int,
    ingredient_ids: Sequence[str],
    catalog: IngredientCatalog,
) -> tuple[list[str], list[Ingredient]]:
    """Every per-recipe problem, without naming the recipe, and its ingredients."""
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
    return problems, ingredients


def parse_recipes(raw: bytes, catalog: IngredientCatalog) -> tuple[Recipe, ...]:
    """Parse the seed file, data/recipes.v1.toml, into recipes in file order.

    Every recipe goes through build_recipe, and on top of that ids must be
    canonical UUIDs and ids and normalized names must be unique. Collects
    every problem before raising, like parse_catalog.
    """
    if not raw.strip():
        raise RecipeError(["the recipe file is empty"])
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise RecipeError([f"the recipe file is not valid TOML: {error}"]) from error

    problems = [
        f"unknown top-level key {key!r}" for key in sorted(data) if key != "recipe"
    ]
    rows = data.get("recipe")
    if not isinstance(rows, list) or not rows:
        problems.append("the recipe file has no [[recipe]] entries")
        rows = []

    recipes: list[Recipe] = []
    seen_ids: set[UUID] = set()
    seen_names: set[str] = set()
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            problems.append(f"recipe #{number} is not a table")
            continue
        where = f"recipe #{number}"
        problems.extend(
            f"{where}: unknown field {field!r}"
            for field in sorted(set(row) - RECIPE_FIELDS)
        )

        recipe_id = _recipe_id(row.get("id"), where, problems)
        if recipe_id is not None:
            if recipe_id in seen_ids:
                problems.append(f"{where}: duplicate recipe id {str(recipe_id)!r}")
            seen_ids.add(recipe_id)
        name = row.get("name")
        if isinstance(name, str) and name.strip():
            if normalize(name) in seen_names:
                problems.append(f"{where}: duplicate recipe name {normalize(name)!r}")
            seen_names.add(normalize(name))
        ingredient_ids = row.get("ingredients")
        if not isinstance(ingredient_ids, list) or not all(
            isinstance(item, str) for item in ingredient_ids
        ):
            problems.append(f"{where}: ingredients must be a list of ingredient ids")
            ingredient_ids = None
        if ingredient_ids is None:
            # Checking an empty list would add a misleading "has no ingredients".
            continue
        if recipe_id is None:
            # No id to name it by, but the other mistakes still show this run.
            found, _ = _check_recipe(
                name=name,  # type: ignore[arg-type]  # _check_recipe checks it
                prep_minutes=row.get("prep_minutes"),  # type: ignore[arg-type]
                cook_minutes=row.get("cook_minutes"),  # type: ignore[arg-type]
                ingredient_ids=ingredient_ids,
                catalog=catalog,
            )
            problems.extend(f"{where}: {problem}" for problem in found)
            continue

        try:
            recipe = build_recipe(
                id=recipe_id,
                name=name,  # type: ignore[arg-type]  # build_recipe checks it
                prep_minutes=row.get("prep_minutes"),  # type: ignore[arg-type]
                cook_minutes=row.get("cook_minutes"),  # type: ignore[arg-type]
                ingredient_ids=ingredient_ids,
                catalog=catalog,
            )
        except RecipeError as error:
            problems.extend(f"{where}: {problem}" for problem in error.problems)
            continue
        recipes.append(recipe)

    if problems:
        raise RecipeError(problems)
    return tuple(recipes)


def _recipe_id(value: object, where: str, problems: list[str]) -> UUID | None:
    """Only the canonical lowercase form, so one id is never spelled two ways."""
    if isinstance(value, str):
        try:
            parsed = UUID(value)
        except ValueError:
            pass
        else:
            if str(parsed) == value:
                return parsed
    problems.append(f"{where}: id must be a lowercase UUID string, got {value!r}")
    return None
