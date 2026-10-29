"""Print the Task 2 gate's query plans for a person to read.

    uv run python -m tests.gate load     # sync 50,000 recipes into DATABASE_URL
    uv run python -m tests.gate explain  # EXPLAIN ANALYZE every gate search
    uv run python -m tests.gate bench    # p50/p95/p99 of every gate search

Point DATABASE_URL at an empty, migrated throwaway database (`alembic
upgrade head`): the sync behind `load` refuses to delete recipes already there.
"""

import argparse
import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.database import create_engine
from recipe_app.infra.sync import sync
from tests.domain.factories import DATA_DIR
from tests.gate.benchmark import benchmark, report
from tests.gate.searches import SEARCHES, explain, gate_recipes, search_queries


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tests.gate")
    parser.add_argument("command", choices=["load", "explain", "bench"])
    parser.add_argument(
        "--rounds",
        type=int,
        default=30,
        help="bench: swipe sessions per search, each up to 3 decks (default 30)",
    )
    arguments = parser.parse_args()
    if arguments.rounds < 2:
        # Fewer can leave a search with one sample, and no percentiles.
        parser.error("--rounds must be at least 2")
    engine = create_engine(os.environ["DATABASE_URL"])
    match arguments.command:
        case "load":
            asyncio.run(_load(engine))
        case "explain":
            asyncio.run(_explain(engine))
        case "bench":
            asyncio.run(_bench(engine, arguments.rounds))


async def _load(engine: AsyncEngine) -> None:
    catalog = load_catalog(DATA_DIR)
    recipes = gate_recipes(catalog, load_recipes(catalog, DATA_DIR))
    try:
        report = await sync(engine, catalog, recipes, now=datetime.now(UTC))
        # begin(), not connect(): a rolled-back ANALYZE keeps no statistics.
        async with engine.begin() as connection:
            await connection.execute(text("ANALYZE"))
    finally:
        await engine.dispose()
    print(f"synced {report.recipes} recipes and analyzed every table")


async def _explain(engine: AsyncEngine) -> None:
    catalog = load_catalog(DATA_DIR)
    try:
        async with engine.connect() as connection:
            for name in SEARCHES:
                for part, query in search_queries(name, catalog).items():
                    result = await connection.exec_driver_sql(
                        *explain("EXPLAIN (ANALYZE, BUFFERS)", query, engine.dialect)
                    )
                    print(f"\n## {name}: {part}\n")
                    print("\n".join(line for (line,) in result))
    finally:
        await engine.dispose()


async def _bench(engine: AsyncEngine, rounds: int) -> None:
    try:
        results = await benchmark(engine, rounds=rounds)
    finally:
        await engine.dispose()
    print(report(results))


if __name__ == "__main__":
    main()
