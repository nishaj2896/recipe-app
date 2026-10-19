"""The v1 wire format. Domain objects never leave the API layer as they are.

Requests reject unknown fields; responses may gain fields, so clients must
ignore fields they don't recognise.
"""

from collections.abc import Hashable
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from pydantic_core import PydanticCustomError

from recipe_app.domain.catalog import MAX_ID_LENGTH, SLUG, Diet
from recipe_app.domain.cursor import MAX_CURSOR_LENGTH
from recipe_app.domain.deck import MAX_DECK_SIZE
from recipe_app.domain.matching import IgnoredReason

MAX_INGREDIENT_IDS = 50
MAX_EXCLUDED_STAPLES = 100
MAX_HIDDEN_RECIPE_IDS = 200
MAX_TIME_FILTER_MINUTES = 600


def _unique[T: Hashable](items: list[T]) -> list[T]:
    seen: set[T] = set()
    for item in items:
        if item in seen:
            raise PydanticCustomError(
                "unique_items", "duplicate item {item}", {"item": repr(str(item))}
            )
        seen.add(item)
    return items


IngredientId = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=MAX_ID_LENGTH, pattern=f"^{SLUG.pattern}$"
    ),
]
_UNIQUE = {"uniqueItems": True}


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingredient_ids: Annotated[
        list[IngredientId],
        Field(min_length=1, max_length=MAX_INGREDIENT_IDS, json_schema_extra=_UNIQUE),
        AfterValidator(_unique),
    ]
    excluded_staples: Annotated[
        list[IngredientId],
        Field(max_length=MAX_EXCLUDED_STAPLES, json_schema_extra=_UNIQUE),
        AfterValidator(_unique),
    ] = []
    diet: Diet | None = None
    max_total_minutes: (
        Annotated[int, Field(ge=1, le=MAX_TIME_FILTER_MINUTES, strict=True)] | None
    ) = None
    hidden_recipe_ids: Annotated[
        list[UUID],
        Field(max_length=MAX_HIDDEN_RECIPE_IDS, json_schema_extra=_UNIQUE),
        AfterValidator(_unique),
    ] = []
    limit: Annotated[int, Field(ge=1, le=MAX_DECK_SIZE, strict=True)] = MAX_DECK_SIZE
    cursor: Annotated[str, Field(min_length=1, max_length=MAX_CURSOR_LENGTH)] | None = (
        None
    )


class IngredientRef(BaseModel):
    id: str
    name: str


class IgnoredIngredient(BaseModel):
    id: str
    name: str
    reason: IgnoredReason


class Tier(StrEnum):
    SCORED = "scored"
    ALL_STAPLES = "all_staples"


class RecipeCard(BaseModel):
    id: UUID
    name: str
    tier: Tier
    match_percentage: Annotated[float, Field(ge=0, le=100)] | None = Field(
        description="Share of core weight matched; null on all-staples cards."
    )
    matched_ingredients: list[IngredientRef]
    missing_ingredients: list[IngredientRef]
    assumed_staples: list[IngredientRef]
    prep_minutes: int
    cook_minutes: int
    total_minutes: int
    diet: Diet


class SearchResponse(BaseModel):
    results: list[RecipeCard]
    next_cursor: str | None
    ignored_ingredients: list[IgnoredIngredient]


class RecipeDetail(BaseModel):
    id: UUID
    name: str
    prep_minutes: int
    cook_minutes: int
    total_minutes: int
    diet: Diet
    ingredients: list[IngredientRef]


class CategoryRef(BaseModel):
    id: str
    name: str


class CatalogIngredient(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, validate_by_name=True)

    id: str
    name: str
    ingredient_class: Literal["A", "B", "S"] = Field(alias="class")
    kind: Literal["fresh", "pantry"] | None
    category: CategoryRef
    diet: Diet
    search_terms: list[str]


class IngredientsResponse(BaseModel):
    ingredients: list[CatalogIngredient]


class StapleCategory(BaseModel):
    id: str
    name: str
    staples: list[IngredientRef]


class StapleKindGroup(BaseModel):
    kind: Literal["fresh", "pantry"]
    categories: list[StapleCategory]


class StaplesResponse(BaseModel):
    groups: list[StapleKindGroup]


class Health(BaseModel):
    status: Literal["ok"]


class FieldError(BaseModel):
    field: str
    message: str


class Problem(BaseModel):
    """RFC 9457 problem details; every error response uses this body."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    errors: list[FieldError] | None = None
