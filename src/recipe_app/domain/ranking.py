"""Filtering and ordering matched recipes (ADR-0003 rules 5 and 6)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from recipe_app.domain.catalog import Diet
from recipe_app.domain.matching import (
    AllStaplesMatch,
    Pantry,
    ScoredMatch,
    match_recipe,
)
from recipe_app.domain.recipe import Recipe


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """The request's filters; None means the filter wasn't sent."""

    diet: Diet | None = None
    max_total_minutes: int | None = None
    hidden_recipe_ids: frozenset[UUID] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class Ranking:
    """Both tiers, each fully sorted; deck assembly (step 7) takes it from here."""

    scored: tuple[ScoredMatch, ...]
    all_staples: tuple[AllStaplesMatch, ...]


def scored_sort_key(match: ScoredMatch) -> tuple[int, int, UUID]:
    """Highest score first, then shortest, then recipe id (ADR-0003 rule 5)."""
    return (-match.score_int, match.recipe.total_minutes, match.recipe.id)


def all_staples_sort_key(match: AllStaplesMatch) -> tuple[int, UUID]:
    """Shortest first, then recipe id (ADR-0003 rule 5)."""
    return (match.recipe.total_minutes, match.recipe.id)


def rank(recipes: Iterable[Recipe], pantry: Pantry, filters: SearchFilters) -> Ranking:
    """Filter first, then match and sort each tier (ADR-0003 rule 6)."""
    scored: list[ScoredMatch] = []
    all_staples: list[AllStaplesMatch] = []
    for recipe in recipes:
        if not passes_filters(recipe, filters):
            continue
        match = match_recipe(recipe, pantry)
        if isinstance(match, ScoredMatch):
            scored.append(match)
        elif isinstance(match, AllStaplesMatch):
            all_staples.append(match)

    return Ranking(
        scored=tuple(sorted(scored, key=scored_sort_key)),
        all_staples=tuple(sorted(all_staples, key=all_staples_sort_key)),
    )


def passes_filters(recipe: Recipe, filters: SearchFilters) -> bool:
    """Whether the recipe survives diet, time and hidden ids (ADR-0003 rule 6)."""
    if filters.diet is not None and not filters.diet.allows(recipe.diet):
        return False
    if (
        filters.max_total_minutes is not None
        and recipe.total_minutes > filters.max_total_minutes
    ):
        return False
    return recipe.id not in filters.hidden_recipe_ids
