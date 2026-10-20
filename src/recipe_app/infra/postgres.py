"""The Postgres RecipeRepository (ADR-0005 rules 4 and 5).

SQL finds the candidates; the domain still ranks them, so ADR-0003 keeps one
implementation. Rows become domain objects through the catalog this process
loaded, never through a second model of a recipe.
"""

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    RowMapping,
    and_,
    exists,
    func,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import Diet, IngredientCatalog
from recipe_app.domain.matching import Pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.tables import recipe_ingredients, recipes

logger = logging.getLogger(__name__)

# Each recipe with its ingredient ids in the order a cook gathers them.
_INGREDIENT_IDS = (
    select(
        func.array_agg(
            aggregate_order_by(
                recipe_ingredients.c.ingredient_id, recipe_ingredients.c.position
            )
        )
    )
    .where(recipe_ingredients.c.recipe_id == recipes.c.id)
    .scalar_subquery()
    .label("ingredient_ids")
)
_RECIPE = select(
    recipes.c.id,
    recipes.c.name,
    recipes.c.prep_minutes,
    recipes.c.cook_minutes,
    _INGREDIENT_IDS,
)


class PostgresRecipeRepository:
    """Reads recipes; only `recipe-app db sync` writes them (ADR-0005 rule 2)."""

    def __init__(self, engine: AsyncEngine, catalog: IngredientCatalog) -> None:
        self._engine = engine
        self._catalog = catalog

    async def get(self, recipe_id: UUID) -> Recipe | None:
        async with self._engine.connect() as connection:
            row = (
                (await connection.execute(_RECIPE.where(recipes.c.id == recipe_id)))
                .mappings()
                .one_or_none()
            )
        return None if row is None else self._to_recipe(row)

    async def candidates(
        self, pantry: Pantry, filters: SearchFilters
    ) -> Sequence[Recipe]:
        statement = _RECIPE.where(
            or_(_uses_any(pantry.have), _all_staples_for(pantry.out_of)),
            *_filters(filters),
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement)).mappings().all()
        found = (self._to_recipe(row) for row in rows)
        return [recipe for recipe in found if recipe is not None]

    def _to_recipe(self, row: RowMapping) -> Recipe | None:
        ingredient_ids: list[str] = row["ingredient_ids"]
        missing = [item for item in ingredient_ids if item not in self._catalog.by_id]
        if missing:
            # A sync added ingredients after this process loaded its catalog; the
            # recipe shows again after the restart that follows (ADR-0005 risk).
            logger.warning(
                "skipping recipe %s: ingredients %s are not in catalog %s",
                row["id"],
                missing,
                self._catalog.content_hash,
            )
            return None
        # Built directly: the sync already ran build_recipe's checks on this data.
        return Recipe(
            id=row["id"],
            name=row["name"],
            prep_minutes=row["prep_minutes"],
            cook_minutes=row["cook_minutes"],
            ingredients=tuple(self._catalog.by_id[item] for item in ingredient_ids),
        )


def _uses_any(ingredient_ids: frozenset[str]) -> ColumnElement[bool]:
    """Served by ix_recipe_ingredients_ingredient_id_recipe_id."""
    return recipes.c.id.in_(
        select(recipe_ingredients.c.recipe_id).where(
            recipe_ingredients.c.ingredient_id.in_(sorted(ingredient_ids))
        )
    )


def _all_staples_for(out_of: frozenset[str]) -> ColumnElement[bool]:
    """All staples, and none of them unticked (ADR-0003 rule 3)."""
    return and_(
        recipes.c.all_staples,
        ~exists().where(
            recipe_ingredients.c.recipe_id == recipes.c.id,
            recipe_ingredients.c.ingredient_id.in_(sorted(out_of)),
        ),
    )


def _filters(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """The same rules as ranking.passes_filters, on the stored columns."""
    conditions: list[ColumnElement[bool]] = [true()]
    if filters.diet is not None:
        allowed = [diet.value for diet in Diet if filters.diet.allows(diet)]
        conditions.append(recipes.c.diet.in_(allowed))
    if filters.max_total_minutes is not None:
        conditions.append(recipes.c.total_minutes <= filters.max_total_minutes)
    if filters.hidden_recipe_ids:
        conditions.append(recipes.c.id.not_in(sorted(filters.hidden_recipe_ids)))
    return conditions
