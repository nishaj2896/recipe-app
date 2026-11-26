"""The composition root: build_app reads settings, then the database at startup."""

import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update

from recipe_app.api.app import build_app
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.catalog_store import CatalogNotSyncedError, WeightsNotSyncedError
from recipe_app.infra.config import ConfigError
from recipe_app.infra.database import create_engine
from recipe_app.infra.tables import recipes
from tests.apps import AppFactory, client_for
from tests.databases import sync_seed

pytestmark = pytest.mark.anyio

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()
SEARCHES = [
    {"ingredient_ids": ["potato", "peas"]},
    {"ingredient_ids": ["kingfish"]},
    {"ingredient_ids": ["paneer", "rice"], "diet": "vegetarian"},
    {"ingredient_ids": ["egg"], "max_total_minutes": 20, "limit": 5},
]


@pytest.fixture(autouse=True)
def bare_app_logger() -> Iterator[logging.Logger]:
    """configure_logging changes the root, app and uvicorn loggers; each test
    gets them back as they were."""
    names = ("", "recipe_app", "uvicorn", "uvicorn.access")
    loggers = [logging.getLogger(name) for name in names]
    saved = [(lg.handlers[:], lg.level, lg.propagate, lg.disabled) for lg in loggers]
    app_logger = loggers[1]
    app_logger.setLevel(logging.NOTSET)
    yield app_logger
    for lg, (handlers, level, propagate, disabled) in zip(loggers, saved, strict=True):
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


@asynccontextmanager
async def started(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run the app's lifespan, as uvicorn does, around a client."""
    async with app.router.lifespan_context(app), client_for(app) as client:
        yield client


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("CURSOR_SIGNING_KEYS", json.dumps({"a": KEY}))
    monkeypatch.setenv("CURSOR_ACTIVE_KID", "a")
    return monkeypatch


def log_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line]


async def test_build_app_logs_the_catalog_hash_to_stdout(
    settings: pytest.MonkeyPatch,
    seeded_database_url: str,
    real_catalog: IngredientCatalog,
    capfd: pytest.CaptureFixture[str],
    bare_app_logger: logging.Logger,
) -> None:
    """ADR-0002 rule 7: you can always tell which catalog a pod runs.

    Reads stdout, not caplog: caplog sees records that no handler would print.
    Every line is one JSON object (ADR-0013 rule 4).
    """
    settings.setenv("DATABASE_URL", seeded_database_url)

    async with started(build_app()):
        pass

    lines = log_lines(capfd.readouterr().out)
    loaded = [line for line in lines if "loaded catalog" in str(line["message"])]
    assert len(loaded) == 1
    assert real_catalog.content_hash in str(loaded[0]["message"])
    assert loaded[0]["level"] == "INFO"
    assert loaded[0]["logger"] == "recipe_app.api.app"


async def test_log_format_text_keeps_readable_lines(
    settings: pytest.MonkeyPatch,
    seeded_database_url: str,
    capfd: pytest.CaptureFixture[str],
    bare_app_logger: logging.Logger,
) -> None:
    settings.setenv("DATABASE_URL", seeded_database_url)
    settings.setenv("LOG_FORMAT", "text")

    async with started(build_app()):
        pass

    assert "INFO recipe_app.api.app: loaded catalog" in capfd.readouterr().out


def test_build_app_logs_its_settings_without_secrets(
    settings: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    bare_app_logger: logging.Logger,
) -> None:
    """ADR-0013 rule 8: the first thing to check on a misbehaving pod."""
    settings.setenv("DATABASE_URL", "postgresql+asyncpg://u:hunter2@db:5432/app")
    settings.delenv("API_DOCS", raising=False)

    build_app()

    stdout = capfd.readouterr().out
    assert (
        "starting with DATABASE_URL=postgresql+asyncpg://u:***@db:5432/app, "
        "CURSOR_ACTIVE_KID=a, CURSOR_SIGNING_KEYS=1 key (a), API_DOCS=false, "
        "DATABASE_CONNECT_TIMEOUT_SECONDS=3, DATABASE_POOL_TIMEOUT_SECONDS=2, "
        "DATABASE_STATEMENT_TIMEOUT_SECONDS=3, DATABASE_POOL_SIZE=5, "
        "DATABASE_POOL_MAX_OVERFLOW=5, RETRY_AFTER_SECONDS=2, "
        "LOG_LEVEL=INFO, LOG_FORMAT=json"
    ) in stdout
    assert "hunter2" not in stdout
    assert KEY not in stdout


async def test_the_database_app_answers_like_the_file_app(
    settings: pytest.MonkeyPatch, seeded_database_url: str, make_app: AppFactory
) -> None:
    """Same catalog bytes and ETags, same cards: Postgres changed nothing users see."""
    settings.setenv("DATABASE_URL", seeded_database_url)

    async with (
        client_for(make_app()) as from_files,
        started(build_app()) as from_database,
    ):
        for path in ("/api/v1/ingredients", "/api/v1/staples"):
            expected = await from_files.get(path)
            actual = await from_database.get(path)
            assert actual.status_code == 200
            assert actual.content == expected.content
            assert actual.headers["etag"] == expected.headers["etag"]
        for search in SEARCHES:
            expected = await from_files.post("/api/v1/recipes/search", json=search)
            actual = await from_database.post("/api/v1/recipes/search", json=search)
            assert actual.status_code == 200
            # Cursors differ: they carry this app's own keys and clock.
            assert actual.json()["results"] == expected.json()["results"]
        recipe_id = expected.json()["results"][0]["id"]
        detail = f"/api/v1/recipes/{recipe_id}"
        actual = await from_database.get(detail)
        assert actual.status_code == 200
        assert actual.json() == (await from_files.get(detail)).json()


async def test_build_app_refuses_to_start_on_an_unsynced_database(
    settings: pytest.MonkeyPatch, migrated_database_url: str
) -> None:
    settings.setenv("DATABASE_URL", migrated_database_url)
    app = build_app()

    with pytest.raises(CatalogNotSyncedError, match="recipe-app db sync"):
        async with started(app):
            pass


async def test_build_app_refuses_to_start_before_the_weights_are_synced(
    settings: pytest.MonkeyPatch,
    migrated_database_url: str,
    real_catalog: IngredientCatalog,
    seed: tuple[Recipe, ...],
) -> None:
    """A migration added the weights as NULL; only a sync fills them (ADR-0007)."""
    await sync_seed(migrated_database_url, real_catalog, seed)
    engine = create_engine(migrated_database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(update(recipes).values(core_weight=None))
    finally:
        await engine.dispose()
    settings.setenv("DATABASE_URL", migrated_database_url)
    app = build_app()

    with pytest.raises(WeightsNotSyncedError, match="recipe-app db sync"):
        async with started(app):
            pass


async def test_build_app_refuses_to_start_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURSOR_SIGNING_KEYS", raising=False)

    with pytest.raises(ConfigError):
        build_app()


async def test_build_app_refuses_to_start_without_a_database_url(
    settings: pytest.MonkeyPatch,
) -> None:
    settings.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ConfigError, match="DATABASE_URL"):
        build_app()


async def test_build_app_refuses_to_start_on_a_bad_docs_flag(
    settings: pytest.MonkeyPatch,
) -> None:
    settings.setenv("DATABASE_URL", "postgresql+asyncpg://u@localhost/db")
    settings.setenv("API_DOCS", "yes")

    with pytest.raises(ConfigError, match="API_DOCS"):
        build_app()


@pytest.mark.parametrize(
    ("flag", "status"), [(None, 404), ("false", 404), ("true", 200)]
)
async def test_build_app_serves_docs_only_when_asked(
    settings: pytest.MonkeyPatch, flag: str | None, status: int
) -> None:
    """No lifespan here: the docs routes don't touch the database."""
    settings.setenv("DATABASE_URL", "postgresql+asyncpg://u@localhost/db")
    if flag is None:
        settings.delenv("API_DOCS", raising=False)
    else:
        settings.setenv("API_DOCS", flag)

    async with client_for(build_app()) as client:
        responses = [await client.get(p) for p in ("/docs", "/redoc", "/openapi.json")]

    assert [r.status_code for r in responses] == [status] * 3
