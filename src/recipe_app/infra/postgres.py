"""The Postgres RecipeRepository (ADR-0005 rules 4 and 5).

SQL finds the candidates; the domain still ranks them, so ADR-0003 keeps one
implementation. Rows become domain objects through the catalog this process
loaded, never through a second model of a recipe.
"""

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    ColumnElement,
    RowMapping,
    Select,
    Text,
    Uuid,
    any_,
    bindparam,
    exists,
    func,
    select,
    union_all,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.sql.elements import CollectionAggregate

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
        return None if row is None else next(iter(self._to_recipes([row])), None)

    async def candidates(
        self, pantry: Pantry, filters: SearchFilters
    ) -> Sequence[Recipe]:
        async with self._engine.connect() as connection:
            rows = (
                (await connection.execute(candidates_query(pantry, filters)))
                .mappings()
                .all()
            )
        return self._to_recipes(rows)

    def _to_recipes(self, rows: Sequence[RowMapping]) -> list[Recipe]:
        """Map rows to recipes, skipping any this process can't build.

        A bad row costs that recipe, never the whole request. The usual cause
        is a sync that added ingredients after this process loaded its catalog;
        those recipes show again after the restart that follows (ADR-0005 risk).
        One warning per call, so a busy pod doesn't log once per recipe.
        """
        found: list[Recipe] = []
        skipped: list[UUID] = []
        missing: set[str] = set()
        for row in rows:
            # array_agg over no rows is NULL; the schema can't forbid that.
            ingredient_ids: list[str] = row["ingredient_ids"] or []
            unknown = {i for i in ingredient_ids if i not in self._catalog.by_id}
            if not ingredient_ids or unknown:
                skipped.append(row["id"])
                missing |= unknown
                continue
            # Built directly: the sync already ran build_recipe's checks on this data.
            found.append(
                Recipe(
                    id=row["id"],
                    name=row["name"],
                    prep_minutes=row["prep_minutes"],
                    cook_minutes=row["cook_minutes"],
                    ingredients=tuple(self._catalog.by_id[i] for i in ingredient_ids),
                )
            )
        if skipped:
            logger.warning(
                "skipped %d recipes catalog %s can't build "
                "(no ingredients, or unknown ingredients %s): %s",
                len(skipped),
                self._catalog.content_hash,
                sorted(missing),
                [str(recipe_id) for recipe_id in skipped[:10]],
            )
        return found


def candidates_query(pantry: Pantry, filters: SearchFilters) -> Select[Any]:
    """The search's SQL; public so the Task 2 gate can EXPLAIN exactly this.

    The two ways in are a UNION of ids, not an OR. Given an OR, Postgres
    tested both conditions against every recipe (issue #34); given a UNION,
    each side looks up its own index.
    """
    return _RECIPE.where(
        recipes.c.id.in_(
            union_all(_uses_any(pantry.have), _all_staples_for(pantry.out_of))
        ),
        *_filters(filters),
    )


def _uses_any(ingredient_ids: frozenset[str]) -> Select[tuple[UUID]]:
    """Served by ix_recipe_ingredients_ingredient_id_recipe_id."""
    return select(recipe_ingredients.c.recipe_id).where(
        recipe_ingredients.c.ingredient_id == _any_text("have", ingredient_ids)
    )


def _all_staples_for(out_of: frozenset[str]) -> Select[tuple[UUID]]:
    """All staples, and none of them unticked (ADR-0003 rule 3).

    Served by ix_recipes_all_staples. Its own alias, so the NOT EXISTS
    correlates here and not with the outer query's recipes.
    """
    staples_only = recipes.alias("staples_only")
    return select(staples_only.c.id).where(
        staples_only.c.all_staples,
        ~exists().where(
            recipe_ingredients.c.recipe_id == staples_only.c.id,
            recipe_ingredients.c.ingredient_id == _any_text("out_of", out_of),
        ),
    )


def _filters(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """The same rules as ranking.passes_filters, on the stored columns."""
    conditions: list[ColumnElement[bool]] = []
    if filters.diet is not None:
        allowed = {diet.value for diet in Diet if filters.diet.allows(diet)}
        conditions.append(recipes.c.diet == _any_text("diets", allowed))
    if filters.max_total_minutes is not None:
        conditions.append(recipes.c.total_minutes <= filters.max_total_minutes)
    if filters.hidden_recipe_ids:
        hidden = bindparam(
            "hidden", sorted(filters.hidden_recipe_ids), type_=ARRAY(Uuid)
        )
        conditions.append(~(recipes.c.id == any_(hidden)))
    return conditions


def _any_text(
    name: str, values: frozenset[str] | set[str]
) -> CollectionAggregate[bool]:
    """`= ANY(:name)` with one array parameter, so the SQL text stays the same
    whatever the list length and asyncpg's prepared-statement cache keeps hitting.
    """
    return any_(bindparam(name, sorted(values), type_=ARRAY(Text)))
