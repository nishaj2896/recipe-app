"""Domain objects to wire schemas, in one place."""

from recipe_app.api.schemas import (
    CatalogIngredient,
    CategoryRef,
    IgnoredIngredient,
    IngredientRef,
    IngredientsResponse,
    RecipeCard,
    RecipeDetail,
    SearchResponse,
    StapleCategory,
    StapleKindGroup,
    StaplesResponse,
    Tier,
)
from recipe_app.domain.catalog import Ingredient, IngredientCatalog
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


def recipe_detail(recipe: Recipe) -> RecipeDetail:
    return RecipeDetail(
        id=recipe.id,
        name=recipe.name,
        prep_minutes=recipe.prep_minutes,
        cook_minutes=recipe.cook_minutes,
        total_minutes=recipe.total_minutes,
        diet=recipe.diet,
        ingredients=_refs(recipe.ingredients),
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
