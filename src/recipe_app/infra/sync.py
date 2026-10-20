"""`recipe-app db sync`: write the checked data files to Postgres (ADR-0005 rule 2).

The sync is the only writer. It runs in one transaction, so a failed run
changes nothing, and it recomputes every derived column on every run.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Table, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.recipe import Recipe
from recipe_app.infra import tables

# Any fixed number works; every sync takes the same one, so two never interleave.
SYNC_LOCK_KEY = 0x5EC1_9E5


class SyncError(ValueError):
    """The files would delete data that is already published; nothing was written."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(f"sync refused:\n{lines}")


@dataclass(frozen=True, slots=True)
class SyncReport:
    categories: int
    ingredients: int
    recipes: int
    content_hash: str


async def sync(
    engine: AsyncEngine,
    catalog: IngredientCatalog,
    recipes: Sequence[Recipe],
    *,
    now: datetime,
) -> SyncReport:
    """Make the database hold exactly these files, or raise and change nothing."""
    async with engine.begin() as connection:
        # Held until commit or rollback; a second sync waits here.
        await connection.execute(select(func.pg_advisory_xact_lock(SYNC_LOCK_KEY)))
        await _refuse_deletions(connection, catalog, recipes)

        await _upsert(
            connection,
            tables.categories,
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "position": item.position,
                    "retired": item.retired,
                }
                for item in catalog.categories.values()
            ],
        )
        await _upsert(
            connection,
            tables.ingredients,
            [
                {
                    "id": item.id,
                    "name": item.name,
                    "class": item.ingredient_class.value,
                    "kind": item.kind.value if item.kind else None,
                    "diet": item.diet.value,
                    "category_id": item.category,
                    "retired": item.retired,
                }
                for item in catalog.by_id.values()
            ],
        )
        await _replace(
            connection,
            tables.ingredient_search_terms,
            [
                {"ingredient_id": item.id, "position": position, "term": term}
                for item in catalog.by_id.values()
                for position, term in enumerate(item.search_terms)
            ],
        )
        await _upsert(
            connection,
            tables.recipes,
            [
                {
                    "id": recipe.id,
                    "name": recipe.name,
                    "prep_minutes": recipe.prep_minutes,
                    "cook_minutes": recipe.cook_minutes,
                    # Derived, so recomputed on every run (ADR-0005 rule 3).
                    "diet": recipe.diet.value,
                    "all_staples": recipe.all_staples,
                }
                for recipe in recipes
            ],
        )
        await _replace(
            connection,
            tables.recipe_ingredients,
            [
                {"recipe_id": recipe.id, "position": position, "ingredient_id": item.id}
                for recipe in recipes
                for position, item in enumerate(recipe.ingredients)
            ],
        )
        await _upsert(
            connection,
            tables.catalog_state,
            [
                {
                    "singleton": True,
                    "content_hash": catalog.content_hash,
                    "synced_at": now,
                }
            ],
            key="singleton",
        )

    return SyncReport(
        categories=len(catalog.categories),
        ingredients=len(catalog.by_id),
        recipes=len(recipes),
        content_hash=catalog.content_hash,
    )


async def _refuse_deletions(
    connection: AsyncConnection,
    catalog: IngredientCatalog,
    recipes: Sequence[Recipe],
) -> None:
    """Ids are published and append-only (ADR-0001 rule 2): retire, never delete."""
    problems: list[str] = []
    for table, label, wanted in (
        (tables.categories, "category", set(catalog.categories)),
        (tables.ingredients, "ingredient", set(catalog.by_id)),
        (tables.recipes, "recipe", {recipe.id for recipe in recipes}),
    ):
        stored = set(await connection.scalars(select(table.c.id)))
        problems.extend(
            f"{label} {str(missing)!r} is in the database but not in the files; "
            "retire it instead of deleting it"
            for missing in sorted(stored - wanted, key=str)
        )
    if problems:
        raise SyncError(problems)


async def _upsert(
    connection: AsyncConnection,
    table: Table,
    rows: list[dict[str, Any]],
    *,
    key: str = "id",
) -> None:
    if not rows:
        return
    statement = insert(table)
    await connection.execute(
        statement.on_conflict_do_update(
            index_elements=[key],
            set_={name: statement.excluded[name] for name in rows[0] if name != key},
        ),
        rows,
    )


async def _replace(
    connection: AsyncConnection, table: Table, rows: Iterable[dict[str, Any]]
) -> None:
    """Child rows have no ids of their own, so the sync rewrites them all."""
    await connection.execute(delete(table))
    rows = list(rows)
    if rows:
        await connection.execute(insert(table), rows)
