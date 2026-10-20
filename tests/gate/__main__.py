"""Print the Task 2 gate's query plans for a person to read.

    uv run python -m tests.gate load     # sync 50,000 recipes into DATABASE_URL
    uv run python -m tests.gate explain  # EXPLAIN ANALYZE every gate search

Point DATABASE_URL at a throwaway database: `load` replaces its recipes.
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
from tests.gate.searches import SEARCHES, explain, gate_recipes, search_query


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m tests.gate")
    parser.add_argument("command", choices=["load", "explain"])
    command = parser.parse_args().command
    engine = create_engine(os.environ["DATABASE_URL"])
    asyncio.run(_load(engine) if command == "load" else _explain(engine))


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
                result = await connection.exec_driver_sql(
                    *explain(
                        "EXPLAIN (ANALYZE, BUFFERS)",
                        search_query(name, catalog),
                        engine.dialect,
                    )
                )
                print(f"\n## {name}\n")
                print("\n".join(line for (line,) in result))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    main()
