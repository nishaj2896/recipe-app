"""The v1 wire format. Domain objects never leave the API layer as they are.

Requests reject unknown fields; responses may gain fields, so clients must
ignore fields they don't recognise.
"""

from collections.abc import Hashable
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from recipe_app.domain.catalog import MAX_ID_LENGTH, SLUG, Diet
from recipe_app.domain.cursor import MAX_CURSOR_LENGTH
from recipe_app.domain.deck import MAX_DECK_SIZE
from recipe_app.domain.matching import IgnoredReason
from recipe_app.domain.tags import Allergen, Course, Cuisine, Mood, Weather
from recipe_app.domain.units import Unit

MAX_INGREDIENT_IDS = 50
MAX_EXCLUDED_STAPLES = 100
MAX_HIDDEN_RECIPE_IDS = 200
MAX_TIME_FILTER_MINUTES = 600
MAX_AVOID_INGREDIENT_IDS = 50
JAIN_DIETS = frozenset({Diet.VEGETARIAN, Diet.VEGAN})


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
    min_total_minutes: (
        Annotated[int, Field(ge=1, le=MAX_TIME_FILTER_MINUTES, strict=True)] | None
    ) = Field(None, description='With `max_total_minutes`; "1 hr+" sends 61.')
    jain: bool = Field(
        False,
        strict=True,
        description="Only Jain recipes; needs `diet` vegetarian or vegan.",
    )
    avoid_allergens: Annotated[
        list[Allergen],
        Field(max_length=len(Allergen), json_schema_extra=_UNIQUE),
        AfterValidator(_unique),
    ] = []
    avoid_ingredient_ids: Annotated[
        list[IngredientId],
        Field(max_length=MAX_AVOID_INGREDIENT_IDS, json_schema_extra=_UNIQUE),
        AfterValidator(_unique),
    ] = []
    courses: Annotated[
        list[Course],
        Field(
            max_length=len(Course),
            json_schema_extra=_UNIQUE,
            description="A recipe needs at least one of them.",
        ),
        AfterValidator(_unique),
    ] = []
    moods: Annotated[
        list[Mood],
        Field(
            max_length=len(Mood),
            json_schema_extra=_UNIQUE,
            description="A recipe needs at least one; more of them ranks it higher.",
        ),
        AfterValidator(_unique),
    ] = []
    weather: Annotated[
        list[Weather],
        Field(
            max_length=len(Weather),
            json_schema_extra=_UNIQUE,
            description="Never removes a recipe; ones that suit any come first.",
        ),
        AfterValidator(_unique),
    ] = []

    @field_validator("min_total_minutes")
    @classmethod
    def _within_max(cls, value: int | None, info: ValidationInfo) -> int | None:
        most = info.data.get("max_total_minutes")
        if value is not None and most is not None and value > most:
            raise PydanticCustomError(
                "time_range", "must not be above max_total_minutes"
            )
        return value

    @field_validator("jain")
    @classmethod
    def _needs_vegetarian(cls, value: bool, info: ValidationInfo) -> bool:
        # A diet that failed validation is missing here; that error is enough.
        if value and "diet" in info.data and info.data["diet"] not in JAIN_DIETS:
            raise PydanticCustomError("jain_diet", "needs diet vegetarian or vegan")
        return value


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


class PlanAhead(BaseModel):
    """A hands-off wait of an hour or more that the times leave out (ADR-0009)."""

    wait_minutes: int
    note: str = Field(
        description='Finishes "Plan ahead: ", so it starts in lower case, '
        'such as "soak overnight".'
    )


class RecipeImage(BaseModel):
    url: str = Field(description="A path on the web origin, versioned by content.")
    alt: str


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
    plan_ahead: PlanAhead | None
    image: RecipeImage | None
    cuisine: Cuisine | None = Field(description="Null until the recipe is tagged.")
    courses: list[Course]
    moods: list[Mood]
    weather_fit: bool = Field(
        description="Suits a requested `weather`, for the weather badge."
    )
    jain: bool = Field(
        description="Vegan or vegetarian with no onion, garlic, roots, "
        "mushrooms or honey (ADR-0012 rule 2)."
    )
    allergens: list[Allergen] = Field(
        description="Best-effort: ready-made ingredients can hide allergens."
    )


class SearchResponse(BaseModel):
    results: list[RecipeCard]
    next_cursor: str | None
    ignored_ingredients: list[IgnoredIngredient]


class RecipeIngredient(IngredientRef):
    amount: float | None = Field(
        description="For the recipe's `serves`; null with `unit` when to taste."
    )
    unit: Unit | None


class AllergenSource(BaseModel):
    allergen: Allergen
    ingredients: list[IngredientRef]


class PairCard(BaseModel):
    """Enough of a paired recipe to show it and check it against food rules."""

    id: UUID
    name: str
    total_minutes: int
    courses: list[Course]
    diet: Diet
    jain: bool
    allergens: list[Allergen]
    ingredient_ids: list[str] = Field(
        description="So the app can hide a pick that uses an ingredient the "
        "food rules avoid."
    )
    image: RecipeImage | None


class RecipeDetail(BaseModel):
    id: UUID
    name: str
    prep_minutes: int
    cook_minutes: int
    total_minutes: int
    diet: Diet
    plan_ahead: PlanAhead | None
    serves: int | None = Field(
        description="Servings the amounts are written for; null before a sync."
    )
    ingredients: list[RecipeIngredient]
    steps: list[str]
    image: RecipeImage | None
    cuisine: Cuisine | None = Field(description="Null until the recipe is tagged.")
    courses: list[Course]
    moods: list[Mood]
    jain: bool
    allergens: list[AllergenSource] = Field(
        description="Each allergen with the ingredients that bring it, in "
        "ingredient order. Best-effort: ready-made ingredients can hide allergens."
    )
    pairs_with: list[PairCard] = Field(
        description="Hand-picked recipes to serve alongside, in order. The app "
        "hides any that break the user's food rules (ADR-0012 rule 8)."
    )


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
