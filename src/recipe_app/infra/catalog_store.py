"""Read the ingredient catalog the last sync wrote (ADR-0005 rule 7).

The app loads it once at startup. Its content_hash is the one the sync
stored, so every pod that loaded the same sync agrees on it, and cursors
minted on one pod work on another (ADR-0003 rule 9).
"""

from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import (
    Category,
    Diet,
    Ingredient,
    IngredientCatalog,
    IngredientClass,
    StapleKind,
)
from recipe_app.infra.tables import (
    catalog_state,
    categories,
    ingredient_search_terms,
    ingredients,
)


class CatalogNotSyncedError(RuntimeError):
    """The database has no catalog yet; the app must not start."""

    def __init__(self) -> None:
        super().__init__(
            "the database has no catalog; run `recipe-app db sync` before starting"
        )


async def read_catalog(engine: AsyncEngine) -> IngredientCatalog:
    """The synced catalog, retired entries included, like parse_catalog's.

    One repeatable-read transaction, so a sync committing halfway through
    can't mix two catalogs.
    """
    async with engine.connect() as connection:
        await connection.execution_options(isolation_level="REPEATABLE READ")
        content_hash = await connection.scalar(select(catalog_state.c.content_hash))
        if content_hash is None:
            raise CatalogNotSyncedError
        category_rows = await connection.execute(
            select(categories).order_by(categories.c.position)
        )
        term_rows = await connection.execute(
            select(ingredient_search_terms).order_by(
                ingredient_search_terms.c.ingredient_id,
                ingredient_search_terms.c.position,
            )
        )
        # Mappings, because "class" is a Python keyword and can't be an attribute.
        ingredient_rows = (
            await connection.execute(select(ingredients).order_by(ingredients.c.id))
        ).mappings()

    # Built directly: the sync ran parse_catalog's checks before writing.
    by_category = {
        row.id: Category(
            id=row.id, name=row.name, position=row.position, retired=row.retired
        )
        for row in category_rows
    }
    terms: dict[str, list[str]] = {}
    for row in term_rows:
        terms.setdefault(row.ingredient_id, []).append(row.term)
    by_id = {
        row["id"]: Ingredient(
            id=row["id"],
            name=row["name"],
            ingredient_class=IngredientClass(row["class"]),
            kind=None if row["kind"] is None else StapleKind(row["kind"]),
            diet=Diet(row["diet"]),
            category=row["category_id"],
            search_terms=tuple(terms.get(row["id"], ())),
            retired=row["retired"],
        )
        for row in ingredient_rows
    }
    return IngredientCatalog(
        by_id=MappingProxyType(by_id),
        categories=MappingProxyType(by_category),
        content_hash=content_hash,
    )
