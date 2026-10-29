"""The Task 2 gate, kept for Task 3: on 50,000 recipes, the search reaches
recipes through its indexes and ranks what the in-memory repository ranks.

Asserts plan shapes, never timings: CI machines are too noisy for those.
`python -m tests.gate` prints the full EXPLAIN ANALYZE for a person to read.
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.cursor import Position
from recipe_app.domain.deck import MAX_DECK_SIZE, Deck, position_after
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.database import create_engine
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.infra.postgres import PostgresRecipeRepository
from tests.gate.searches import SEARCHES, explain, search_queries

pytestmark = pytest.mark.anyio

INGREDIENT_INDEX = "ix_recipe_ingredients_ingredient_id_recipe_id"
ALL_STAPLES_INDEX = "ix_recipes_all_staples"
PAGE = MAX_DECK_SIZE + 1


@pytest.fixture
async def engine(gate_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(gate_database_url)
    yield engine
    await engine.dispose()


@pytest.mark.parametrize("search", SEARCHES)
async def test_the_scored_tier_finds_recipes_through_the_ingredient_index(
    engine: AsyncEngine, real_catalog: IngredientCatalog, search: str
) -> None:
    """Never a Seq Scan on recipe_ingredients: at 430,000 rows it's the table
    a careless rewrite would read whole.
    """
    nodes = await _nodes_of(engine, search_queries(search, real_catalog)["scored"])

    assert INGREDIENT_INDEX in {node.get("Index Name") for node in nodes}
    assert "recipe_ingredients" not in _seq_scanned(nodes)


@pytest.mark.parametrize("search", SEARCHES)
async def test_the_all_staples_tier_reads_only_its_partial_index(
    engine: AsyncEngine, real_catalog: IngredientCatalog, search: str
) -> None:
    query = search_queries(search, real_catalog)["all staples"]
    nodes = await _nodes_of(engine, query)

    assert ALL_STAPLES_INDEX in {node.get("Index Name") for node in nodes}
    assert not _seq_scanned(nodes)


@pytest.mark.parametrize("search", SEARCHES)
async def test_the_search_is_never_jit_compiled(
    engine: AsyncEngine, real_catalog: IngredientCatalog, search: str
) -> None:
    """Compiling cost more than running, up to 700 ms (issue #34)."""
    for query in search_queries(search, real_catalog).values():
        assert "JIT" not in await _plan(engine, query)


@pytest.mark.parametrize("search", SEARCHES)
async def test_postgres_ranks_what_memory_ranks_at_scale(
    engine: AsyncEngine,
    real_catalog: IngredientCatalog,
    memory_repository: InMemoryRecipeRepository,
    search: str,
) -> None:
    """The first three decks' worth of each tier, page by page (ADR-0007 rule 6)."""
    gate_search = SEARCHES[search]
    pantry = gate_search.pantry(real_catalog)
    postgres = PostgresRecipeRepository(engine, real_catalog)

    after = Position()
    for _ in range(3):
        found = await postgres.ranked(pantry, gate_search.filters, after, PAGE)
        expected = await memory_repository.ranked(
            pantry, gate_search.filters, after, PAGE
        )
        assert found == expected
        assert found.scored
        after = position_after(Deck(found.scored, found.all_staples), after)


@pytest.fixture(scope="module")
def memory_repository(gate_seed: tuple[Recipe, ...]) -> InMemoryRecipeRepository:
    return InMemoryRecipeRepository(gate_seed)


async def _nodes_of(engine: AsyncEngine, query: Select[Any]) -> list[dict[str, Any]]:
    return list(_nodes((await _plan(engine, query))["Plan"]))


def _seq_scanned(nodes: list[dict[str, Any]]) -> list[str]:
    return [node["Relation Name"] for node in nodes if node["Node Type"] == "Seq Scan"]


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
