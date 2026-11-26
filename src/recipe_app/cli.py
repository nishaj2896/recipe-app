"""The `recipe-app` command: no arguments serves the API; `db sync` loads data;
`openapi` prints the API's OpenAPI document.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from recipe_app.domain.catalog import CatalogError
from recipe_app.domain.recipe import RecipeError
from recipe_app.infra.config import ConfigError, SyncSettings
from recipe_app.infra.data import load_catalog, load_recipe_book
from recipe_app.infra.database import create_engine
from recipe_app.infra.sync import SyncError, sync


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recipe-app")
    commands = parser.add_subparsers(dest="command")
    db = commands.add_parser("db", help="manage the database")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser(
        "sync", help="load data/*.toml into the database (needs DATABASE_URL)"
    )
    commands.add_parser("openapi", help="print the OpenAPI document as JSON")
    args = parser.parse_args(argv)

    if args.command is None:
        _serve()
        return 0
    if args.command == "openapi":
        _print_openapi()
        return 0
    try:
        return asyncio.run(_sync())
    except (ConfigError, CatalogError, RecipeError, SyncError) as error:
        print(error, file=sys.stderr)
        return 1


def _print_openapi() -> None:
    from recipe_app.api.app import openapi_schema

    print(json.dumps(openapi_schema(), indent=2, sort_keys=True))


def _serve() -> None:
    import uvicorn

    uvicorn.run("recipe_app.api.app:build_app", factory=True)


async def _sync() -> int:
    settings = SyncSettings.from_env()
    catalog = load_catalog(settings.data_dir)
    book = load_recipe_book(catalog, settings.data_dir)

    engine = create_engine(settings.url)
    try:
        report = await sync(
            engine, catalog, book.recipes, now=datetime.now(UTC), content=book.content
        )
    finally:
        await engine.dispose()
    print(
        f"synced {report.categories} categories, {report.ingredients} ingredients "
        f"and {report.recipes} recipes (catalog {report.content_hash[:12]})"
    )
    return 0
