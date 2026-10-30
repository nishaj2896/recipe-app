"""Recipes, built from catalog ingredients; diet is computed (ADR-0002 rule 6).

The recipe files are parsed in domain/book.py.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from recipe_app.domain.catalog import (
    Diet,
    Ingredient,
    IngredientCatalog,
    IngredientClass,
)

MAX_TOTAL_MINUTES = 24 * 60

# A wait shorter than an hour fits around the cooking; a week covers any pickle.
MIN_WAIT_MINUTES, MAX_WAIT_MINUTES = 60, 7 * 24 * 60
MAX_WAIT_NOTE_LENGTH = 40
PLAN_AHEAD_FIELDS = frozenset({"wait_minutes", "note"})


@dataclass(frozen=True, slots=True)
class PlanAhead:
    """A hands-off wait of an hour or more that the times leave out (ADR-0009).

    `note` finishes "Plan ahead: ", so it has no capital first letter and no full
    stop: "soak overnight".
    """

    wait_minutes: int
    note: str


@dataclass(frozen=True, slots=True)
class Recipe:
    """A recipe made only of real catalog ingredients; build it with build_recipe.

    Prep and cook time count hands-on work only; waiting such as soaking,
    fermenting, marinating, resting, chilling or freezing is left out.
    """

    id: UUID
    name: str
    prep_minutes: int
    cook_minutes: int
    ingredients: tuple[Ingredient, ...]
    plan_ahead: PlanAhead | None = None

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
    plan_ahead: object = None,
) -> Recipe:
    """Resolve every ingredient id against the catalog and check every rule.

    Collects every problem before raising, like parse_catalog, so a seed file
    with several mistakes shows them all in one run.
    """
    problems, ingredients = check_recipe(
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredient_ids=ingredient_ids,
        catalog=catalog,
    )
    wait = check_plan_ahead(plan_ahead, problems)
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
        plan_ahead=wait,
    )


def check_plan_ahead(value: object, problems: list[str]) -> PlanAhead | None:
    """The `plan_ahead` table as written in a recipe file, or None when absent.

    Adds every problem to `problems`, without naming the recipe.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        problems.append("plan_ahead must be a table")
        return None
    before = len(problems)
    problems.extend(
        f"plan_ahead: unknown field {field!r}"
        for field in sorted(set(value) - PLAN_AHEAD_FIELDS)
    )
    minutes, note = value.get("wait_minutes"), value.get("note")
    # type(...) is int, not isinstance: True is an int too, and means nothing here.
    if type(minutes) is not int or not (
        MIN_WAIT_MINUTES <= minutes <= MAX_WAIT_MINUTES
    ):
        problems.append(
            "plan_ahead wait_minutes must be a whole number from "
            f"{MIN_WAIT_MINUTES} to {MAX_WAIT_MINUTES}"
        )
    if (
        not isinstance(note, str)
        or not note
        or len(note) > MAX_WAIT_NOTE_LENGTH
        or note != " ".join(note.split())
        or note[0].isupper()
        or note.endswith(".")
    ):
        problems.append(
            f"plan_ahead note must be 1 to {MAX_WAIT_NOTE_LENGTH} characters, "
            "single-spaced, must not start with a capital letter or end with a "
            "full stop"
        )
    if len(problems) > before:
        return None
    return PlanAhead(wait_minutes=minutes, note=note)  # type: ignore[arg-type]  # checked


def check_recipe(
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
