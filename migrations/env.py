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
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata)
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
