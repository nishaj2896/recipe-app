"""The `recipe-app` command: `serve` (or no arguments) serves the API;
`db sync` loads data; `openapi` prints the API's OpenAPI document.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from recipe_app.domain.catalog import CatalogError
from recipe_app.domain.recipe import RecipeError
from recipe_app.infra.config import ApiSettings, ConfigError, SyncSettings
from recipe_app.infra.data import load_catalog, load_recipe_book
from recipe_app.infra.database import create_engine
from recipe_app.infra.logs import configure_logging
from recipe_app.infra.sync import SyncError, sync


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="recipe-app")
    commands = parser.add_subparsers(dest="command")
    db = commands.add_parser("db", help="manage the database")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser(
        "sync", help="load data/*.toml into the database (needs DATABASE_URL)"
    )
    commands.add_parser(
        "serve", help="serve the API with the limits from the settings (the default)"
    )
    commands.add_parser("openapi", help="print the OpenAPI document as JSON")
    args = parser.parse_args(argv)

    if args.command in (None, "serve"):
        try:
            _serve()
        except ConfigError as error:
            print(error, file=sys.stderr)
            return 1
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
    """uvicorn with every limit from ApiSettings (ADR-0013 rule 7).

    uvicorn's own logging config is skipped: configure_logging owns every
    handler, so the server's lines are JSON from its first one.
    """
    import uvicorn

    settings = ApiSettings.from_env()
    configure_logging(settings.log_level, settings.log_format)
    uvicorn.run(
        "recipe_app.api.app:build_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=1,
        log_config=None,
        access_log=False,
        # After SIGTERM, in-flight requests get this long; then the server
        # closes them and exits. Kubernetes kills at 30 s by default.
        timeout_graceful_shutdown=round(settings.shutdown_grace),
        # Longer than a load balancer's idle timeout (60 s on most), so the
        # balancer, not the app, closes an idle connection. The other way
        # round, it can send a request on a connection the app is closing and
        # answer the client 502.
        timeout_keep_alive=round(settings.keep_alive),
    )


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
