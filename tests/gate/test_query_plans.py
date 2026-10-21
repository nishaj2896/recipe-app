"""The Task 2 gate: on 50,000 recipes, the search reaches recipes through
its indexes and returns what the in-memory repository returns.

Asserts plan shapes, never timings: CI machines are too noisy for those.
`python -m tests.gate` prints the full EXPLAIN ANALYZE for a person to read.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.database import create_engine
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.infra.postgres import PostgresRecipeRepository
from tests.gate.searches import SEARCHES, explain, search_query

pytestmark = pytest.mark.anyio

INGREDIENT_INDEX = "ix_recipe_ingredients_ingredient_id_recipe_id"
ALL_STAPLES_INDEX = "ix_recipes_all_staples"


@pytest.fixture
async def engine(gate_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(gate_database_url)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize("search", SEARCHES)
async def test_the_search_finds_recipes_through_its_indexes(
    engine: AsyncEngine, real_catalog: IngredientCatalog, search: str
) -> None:
    """Issue #34: given an OR of the two ways in, Postgres tested every recipe.

    Never a Seq Scan on recipe_ingredients either: at 430,000 rows it's the
    table a careless rewrite would read whole.
    """
    plan = await _plan(engine, search_query(search, real_catalog))

    nodes = list(_nodes(plan["Plan"]))
    indexes = {node.get("Index Name") for node in nodes}
    assert {INGREDIENT_INDEX, ALL_STAPLES_INDEX} <= indexes
    scanned = [
        node["Relation Name"] for node in nodes if node["Node Type"] == "Seq Scan"
    ]
    assert "recipe_ingredients" not in scanned


@pytest.mark.parametrize("search", SEARCHES)
async def test_the_search_is_never_jit_compiled(
    engine: AsyncEngine, real_catalog: IngredientCatalog, search: str
) -> None:
    """Compiling cost more than running, up to 700 ms (issue #34)."""
    plan = await _plan(engine, search_query(search, real_catalog))

    assert "JIT" not in plan


@pytest.mark.parametrize("search", SEARCHES)
async def test_postgres_finds_what_memory_finds_at_scale(
    engine: AsyncEngine,
    real_catalog: IngredientCatalog,
    gate_seed: tuple[Recipe, ...],
    memory_repository: InMemoryRecipeRepository,
    search: str,
) -> None:
    ingredient_ids, filters = SEARCHES[search]
    pantry = resolve_pantry(
        ingredient_ids=ingredient_ids, excluded_staples=[], catalog=real_catalog
    )
    postgres = PostgresRecipeRepository(engine, real_catalog)

    found = await postgres.candidates(pantry, filters)
    expected = await memory_repository.candidates(pantry, filters)

    assert sorted(recipe.id for recipe in found) == sorted(
        recipe.id for recipe in expected
    )
    assert 0 < len(found) < len(gate_seed)


@pytest.fixture(scope="module")
def memory_repository(gate_seed: tuple[Recipe, ...]) -> InMemoryRecipeRepository:
    return InMemoryRecipeRepository(gate_seed)


async def _plan(engine: AsyncEngine, query: Select[Any]) -> dict[str, Any]:
    async with engine.connect() as connection:
        result = await connection.exec_driver_sql(
            *explain("EXPLAIN (FORMAT JSON)", query, engine.dialect)
        )
        [[plan]] = result.all()
    return plan[0]  # type: ignore[no-any-return]


def _nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("Plans", ()):
        yield from _nodes(child)
