"""Alembic's entry point: applies migrations over asyncpg.

The URL comes from config.attributes["url"] when tests call in, otherwise
from DATABASE_URL, so no password ever lives in alembic.ini.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from recipe_app.infra.config import database_url_from_env
from recipe_app.infra.tables import metadata

config = context.config
# Tests pass configure_logger=False so a migration doesn't reset pytest's logging.
if config.config_file_name is not None and config.attributes.get(
    "configure_logger", True
):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The plugin makes autogenerate and `alembic check` notice a CHECK constraint
# that was added or dropped (matched by name). A changed expression under the
# same name is caught by tests/infra/test_migrations.py instead.
AUTOGENERATE_PLUGINS = [
    "alembic.autogenerate.*",
    "alembic.ext.checkconstraint_byname",
]


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=metadata,
        autogenerate_plugins=AUTOGENERATE_PLUGINS,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = config.attributes.get("url") or database_url_from_env(os.environ)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("offline (--sql) mode is not supported; run against a database")
asyncio.run(run_async_migrations())
