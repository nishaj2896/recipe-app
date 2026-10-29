"""Domain objects to wire schemas, in one place."""

from recipe_app.api.schemas import (
    CatalogIngredient,
    CategoryRef,
    IgnoredIngredient,
    IngredientRef,
    IngredientsResponse,
    RecipeCard,
    RecipeDetail,
    RecipeImage,
    RecipeIngredient,
    SearchResponse,
    StapleCategory,
    StapleKindGroup,
    StaplesResponse,
    Tier,
)
from recipe_app.domain.catalog import Ingredient, IngredientCatalog
from recipe_app.domain.content import RecipeWithContent
from recipe_app.domain.matching import AllStaplesMatch, ScoredMatch
from recipe_app.domain.recipe import Recipe
from recipe_app.services.catalog import listed_ingredients, staple_groups
from recipe_app.services.search import SearchResult


def search_response(result: SearchResult) -> SearchResponse:
    return SearchResponse(
        results=[_scored_card(m) for m in result.deck.scored]
        + [_all_staples_card(m) for m in result.deck.all_staples],
        next_cursor=result.next_cursor,
        ignored_ingredients=[
            IgnoredIngredient(
                id=item.ingredient.id, name=item.ingredient.name, reason=item.reason
            )
            for item in result.ignored
        ],
    )


# Photos are served by the web app (ADR-0008 rule 6).
DISHES_PATH = "/dishes"
IMAGE_VERSION_LENGTH = 12


def recipe_detail(detail: RecipeWithContent) -> RecipeDetail:
    recipe, content = detail.recipe, detail.content
    amounts = content.amounts if content else (None,) * len(recipe.ingredients)
    image = content.image if content else None
    return RecipeDetail(
        id=recipe.id,
        name=recipe.name,
        prep_minutes=recipe.prep_minutes,
        cook_minutes=recipe.cook_minutes,
        total_minutes=recipe.total_minutes,
        diet=recipe.diet,
        serves=content.serves if content else None,
        ingredients=[
            RecipeIngredient(
                id=item.id,
                name=item.name,
                amount=amount.value if amount else None,
                unit=amount.unit if amount else None,
            )
            for item, amount in zip(recipe.ingredients, amounts, strict=True)
        ],
        steps=list(content.steps) if content else [],
        image=None
        if image is None
        else RecipeImage(
            url=f"{DISHES_PATH}/{image.file}?v={image.sha256[:IMAGE_VERSION_LENGTH]}",
            alt=image.alt,
        ),
    )


def ingredients_response(catalog: IngredientCatalog) -> IngredientsResponse:
    return IngredientsResponse(
        ingredients=[
            CatalogIngredient(
                id=item.id,
                name=item.name,
                ingredient_class=item.ingredient_class.value,
                kind=None if item.kind is None else item.kind.value,
                category=CategoryRef(
                    id=item.category, name=catalog.categories[item.category].name
                ),
                diet=item.diet,
                search_terms=list(item.search_terms),
            )
            for item in listed_ingredients(catalog)
        ]
    )


def staples_response(catalog: IngredientCatalog) -> StaplesResponse:
    return StaplesResponse(
        groups=[
            StapleKindGroup(
                kind=group.kind.value,
                categories=[
                    StapleCategory(
                        id=cat.category.id,
                        name=cat.category.name,
                        staples=_refs(cat.ingredients),
                    )
                    for cat in group.categories
                ],
            )
            for group in staple_groups(catalog)
        ]
    )


def _scored_card(match: ScoredMatch) -> RecipeCard:
    return _card(
        match.recipe,
        Tier.SCORED,
        # The only division by 10 for the percentage (ADR-0003 rule 8).
        match_percentage=match.match_tenths / 10,
        matched=match.matched,
        missing=match.missing,
        assumed=match.assumed,
    )


def _all_staples_card(match: AllStaplesMatch) -> RecipeCard:
    return _card(
        match.recipe,
        Tier.ALL_STAPLES,
        match_percentage=None,
        matched=(),
        missing=(),
        assumed=match.assumed,
    )


def _card(
    recipe: Recipe,
    tier: Tier,
    *,
    match_percentage: float | None,
    matched: tuple[Ingredient, ...],
    missing: tuple[Ingredient, ...],
    assumed: tuple[Ingredient, ...],
) -> RecipeCard:
    return RecipeCard(
        id=recipe.id,
        name=recipe.name,
        tier=tier,
        match_percentage=match_percentage,
        matched_ingredients=_refs(matched),
        missing_ingredients=_refs(missing),
        assumed_staples=_refs(assumed),
        prep_minutes=recipe.prep_minutes,
        cook_minutes=recipe.cook_minutes,
        total_minutes=recipe.total_minutes,
        diet=recipe.diet,
    )


def _refs(items: tuple[Ingredient, ...]) -> list[IngredientRef]:
    return [IngredientRef(id=item.id, name=item.name) for item in items]
