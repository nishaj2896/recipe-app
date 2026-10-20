"""The composition root: build_app reads settings, then the database at startup."""

import base64
import json
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from recipe_app.api.app import build_app
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.infra.catalog_store import CatalogNotSyncedError
from recipe_app.infra.config import ConfigError
from tests.apps import AppFactory, client_for

pytestmark = pytest.mark.anyio

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()
SEARCHES = [
    {"ingredient_ids": ["potato", "peas"]},
    {"ingredient_ids": ["kingfish"]},
    {"ingredient_ids": ["paneer", "rice"], "diet": "vegetarian"},
    {"ingredient_ids": ["egg"], "max_total_minutes": 20, "limit": 5},
]


@pytest.fixture
def bare_app_logger() -> Iterator[logging.Logger]:
    """The `recipe_app` logger as a fresh process has it: no handler, no level."""
    app_logger = logging.getLogger("recipe_app")
    saved = app_logger.handlers[:], app_logger.level
    app_logger.handlers.clear()
    app_logger.setLevel(logging.NOTSET)
    yield app_logger
    app_logger.handlers[:], level = saved
    app_logger.setLevel(level)


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


async def test_build_app_logs_the_catalog_hash_to_stderr(
    settings: pytest.MonkeyPatch,
    seeded_database_url: str,
    real_catalog: IngredientCatalog,
    capfd: pytest.CaptureFixture[str],
    bare_app_logger: logging.Logger,
) -> None:
    """ADR-0002 rule 7: you can always tell which catalog a pod runs.

    Reads stderr, not caplog: caplog sees records that no handler would print.
    """
    settings.setenv("DATABASE_URL", seeded_database_url)

    async with started(build_app()):
        pass

    stderr = capfd.readouterr().err
    assert real_catalog.content_hash in stderr
    assert "INFO recipe_app.api.app" in stderr


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
