"""Matching a search request against recipes (ADR-0001 rule 3, ADR-0003 rule 2)."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

from recipe_app.domain import scoring
from recipe_app.domain.catalog import Ingredient, IngredientCatalog, IngredientClass
from recipe_app.domain.recipe import Recipe


class IgnoredReason(StrEnum):
    RETIRED = "retired"
    NOW_STAPLE = "now_staple"
    NOT_STAPLE = "not_staple"


@dataclass(frozen=True, slots=True)
class Ignored:
    ingredient: Ingredient
    reason: IgnoredReason


@dataclass(frozen=True, slots=True)
class Pantry:
    """What one request says the user has; build it with resolve_pantry.

    `have` holds live class A and B ids, `out_of` the live staples the user
    unticked. `ignored` keeps request order, `ingredient_ids` first.
    """

    have: frozenset[str]
    out_of: frozenset[str]
    ignored: tuple[Ignored, ...]


@dataclass(frozen=True, slots=True)
class ScoredMatch:
    """A recipe with at least one ticked ingredient (ADR-0003 rule 3)."""

    recipe: Recipe
    matched: tuple[Ingredient, ...]
    missing: tuple[Ingredient, ...]
    assumed: tuple[Ingredient, ...]
    score_int: int
    match_tenths: int


@dataclass(frozen=True, slots=True)
class AllStaplesMatch:
    """A recipe whose core is empty for this request: no score, nothing missing."""

    recipe: Recipe
    assumed: tuple[Ingredient, ...]


class PantryError(ValueError):
    """The request names ids the catalog never published; `problems` lists all."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(f"invalid search request:\n{lines}")


def resolve_pantry(
    *,
    ingredient_ids: Sequence[str],
    excluded_staples: Sequence[str],
    catalog: IngredientCatalog,
) -> Pantry:
    """Sort the request's ids into have, out of and ignored (ADR-0001 rule 3).

    Collects every problem before raising, like build_recipe.
    """
    problems: list[str] = []
    have: set[str] = set()
    out_of: set[str] = set()
    ignored: dict[str, Ignored] = {}

    for found in _resolve("ingredient_ids", ingredient_ids, catalog, problems):
        if found.retired:
            ignored.setdefault(found.id, Ignored(found, IgnoredReason.RETIRED))
        elif found.ingredient_class is IngredientClass.STAPLE:
            ignored.setdefault(found.id, Ignored(found, IgnoredReason.NOW_STAPLE))
        else:
            have.add(found.id)

    for found in _resolve("excluded_staples", excluded_staples, catalog, problems):
        if found.retired:
            ignored.setdefault(found.id, Ignored(found, IgnoredReason.RETIRED))
        elif found.ingredient_class is not IngredientClass.STAPLE:
            ignored.setdefault(found.id, Ignored(found, IgnoredReason.NOT_STAPLE))
        else:
            out_of.add(found.id)

    if problems:
        raise PantryError(problems)

    return Pantry(
        have=frozenset(have),
        out_of=frozenset(out_of),
        ignored=tuple(ignored.values()),
    )


def _resolve(
    field: str, ids: Sequence[str], catalog: IngredientCatalog, problems: list[str]
) -> list[Ingredient]:
    found: list[Ingredient] = []
    seen: set[str] = set()
    for ingredient_id in ids:
        if ingredient_id in seen:
            problems.append(f"{field}: duplicate ingredient {ingredient_id!r}")
            continue
        seen.add(ingredient_id)
        ingredient = catalog.by_id.get(ingredient_id)
        if ingredient is None:
            problems.append(f"{field}: unknown ingredient {ingredient_id!r}")
        else:
            found.append(ingredient)
    return found


def match_recipe(
    recipe: Recipe, pantry: Pantry
) -> ScoredMatch | AllStaplesMatch | None:
    """Split one recipe into core and assumed and score it (ADR-0003 rules 2 to 4).

    Returns None when the recipe has core ingredients and none of them match.
    Every list keeps the recipe's own ingredient order.
    """
    core = tuple(item for item in recipe.ingredients if _is_core(item, pantry))
    assumed = tuple(item for item in recipe.ingredients if not _is_core(item, pantry))
    if not core:
        return AllStaplesMatch(recipe=recipe, assumed=assumed)

    matched = tuple(item for item in core if item.id in pantry.have)
    if not matched:
        return None
    missing = tuple(item for item in core if item.id not in pantry.have)

    matched_q = sum(_weight(item) for item in matched)
    core_q = sum(_weight(item) for item in core)
    return ScoredMatch(
        recipe=recipe,
        matched=matched,
        missing=missing,
        assumed=assumed,
        score_int=scoring.score_int(matched_q, core_q),
        match_tenths=scoring.match_tenths(matched_q, core_q),
    )


def _is_core(ingredient: Ingredient, pantry: Pantry) -> bool:
    return (
        ingredient.ingredient_class is not IngredientClass.STAPLE
        or ingredient.id in pantry.out_of
    )


def _weight(ingredient: Ingredient) -> int:
    # Only core ingredients are weighed, so a staple here is an excluded one.
    match ingredient.ingredient_class:
        case IngredientClass.MAIN:
            return scoring.MAIN
        case IngredientClass.SUPPORTING:
            return scoring.SUPPORTING
        case IngredientClass.STAPLE:
            return scoring.EXCLUDED_STAPLE
        case _:
            assert_never(ingredient.ingredient_class)
