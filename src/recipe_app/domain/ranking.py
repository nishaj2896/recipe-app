"""Filtering and ordering matched recipes (ADR-0003 rules 5 and 6, ADR-0012
rules 4 to 6).
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from uuid import UUID

from recipe_app.domain.catalog import Diet
from recipe_app.domain.matching import (
    AllStaplesMatch,
    Pantry,
    ScoredMatch,
    match_recipe,
)
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.tags import Allergen, Course, Mood, Weather


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """The request's filters and mood picks; None or empty means not sent.

    Everything here removes recipes except `weather`, which only moves the
    recipes that suit it forward (ADR-0012 rule 5). `moods` does both: a
    recipe needs one of them, and one with more of them comes first.
    """

    diet: Diet | None = None
    max_total_minutes: int | None = None
    min_total_minutes: int | None = None
    hidden_recipe_ids: frozenset[UUID] = field(default_factory=frozenset)
    jain: bool = False
    avoid_allergens: frozenset[Allergen] = field(default_factory=frozenset)
    avoid_ingredient_ids: frozenset[str] = field(default_factory=frozenset)
    courses: frozenset[Course] = field(default_factory=frozenset)
    moods: frozenset[Mood] = field(default_factory=frozenset)
    weather: frozenset[Weather] = field(default_factory=frozenset)

    @property
    def ranks_by_fit(self) -> bool:
        """Whether any recipe can have a fit above 0."""
        return bool(self.moods or self.weather)


@dataclass(frozen=True, slots=True)
class Ranking:
    """Both tiers, each fully sorted; deck assembly (step 7) takes it from here."""

    scored: tuple[ScoredMatch, ...]
    all_staples: tuple[AllStaplesMatch, ...]


def scored_sort_key(match: ScoredMatch) -> tuple[int, int, int, UUID]:
    """Best fit first, then highest score, then shortest, then recipe id
    (ADR-0012 rule 6).
    """
    return (-match.fit, -match.score_int, match.recipe.total_minutes, match.recipe.id)


def all_staples_sort_key(match: AllStaplesMatch) -> tuple[int, int, UUID]:
    """Best fit first, then shortest, then recipe id (ADR-0012 rule 6)."""
    return (-match.fit, match.recipe.total_minutes, match.recipe.id)


def mood_fit(recipe: Recipe, filters: SearchFilters) -> int:
    """How many of the picked moods the recipe has."""
    return sum(1 for mood in recipe.tags.moods if mood in filters.moods)


def weather_fit(recipe: Recipe, filters: SearchFilters) -> bool:
    """Whether the recipe suits any picked weather."""
    return any(weather in filters.weather for weather in recipe.tags.weather)


def rank(recipes: Iterable[Recipe], pantry: Pantry, filters: SearchFilters) -> Ranking:
    """Filter first, then match, weigh the fit and sort each tier (ADR-0003 rule 6)."""
    scored: list[ScoredMatch] = []
    all_staples: list[AllStaplesMatch] = []
    for recipe in recipes:
        if not passes_filters(recipe, filters):
            continue
        match = match_recipe(recipe, pantry)
        if match is None:
            continue
        fitted = replace(
            match,
            mood_fit=mood_fit(recipe, filters),
            weather_fit=weather_fit(recipe, filters),
        )
        if isinstance(fitted, ScoredMatch):
            scored.append(fitted)
        else:
            all_staples.append(fitted)

    return Ranking(
        scored=tuple(sorted(scored, key=scored_sort_key)),
        all_staples=tuple(sorted(all_staples, key=all_staples_sort_key)),
    )


def passes_filters(recipe: Recipe, filters: SearchFilters) -> bool:
    """Whether the recipe survives every filter (ADR-0003 rule 6, ADR-0012
    rules 4 and 5). Weather never removes a recipe.
    """
    minutes = recipe.total_minutes
    tags = recipe.tags
    return not (
        (filters.diet is not None and not filters.diet.allows(recipe.diet))
        or (
            filters.max_total_minutes is not None
            and minutes > filters.max_total_minutes
        )
        or (
            filters.min_total_minutes is not None
            and minutes < filters.min_total_minutes
        )
        or recipe.id in filters.hidden_recipe_ids
        or (filters.jain and not recipe.jain)
        or not filters.avoid_allergens.isdisjoint(recipe.allergens)
        or any(item.id in filters.avoid_ingredient_ids for item in recipe.ingredients)
        or (filters.courses and filters.courses.isdisjoint(tags.courses))
        or (filters.moods and filters.moods.isdisjoint(tags.moods))
    )
