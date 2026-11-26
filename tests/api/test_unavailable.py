"""The 503 for a database that can't answer now (ADR-0013 rule 1)."""

import logging
from uuid import UUID

import pytest
from fastapi import FastAPI

from recipe_app.api.app import create_app
from recipe_app.api.headers import SECURITY_HEADERS
from recipe_app.api.problems import PROBLEM_MEDIA_TYPE, SERVICE_UNAVAILABLE
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.content import RecipeWithContent
from recipe_app.domain.ranking import Ranking
from recipe_app.domain.recipe_search import Found
from recipe_app.services.ports import RecipeRepository, StoreUnavailableError
from recipe_app.services.search import RecipeService
from tests.apps import KEYS, NOW, client_for

pytestmark = pytest.mark.anyio


class DownRepository:
    async def detail(self, recipe_id: UUID) -> RecipeWithContent | None:
        raise StoreUnavailableError("statement timeout")

    async def ranked(self, *_: object) -> Ranking:
        raise StoreUnavailableError("connection lost (57P01)")

    async def find(self, *_: object) -> Found:
        raise StoreUnavailableError("pool timeout")


REQUESTS = [
    ("POST", "/api/v1/recipes/search", {"ingredient_ids": ["potato"]}),
    ("GET", "/api/v1/recipes/01938e5c-0000-7000-8000-000000000000", None),
]


def down_app(catalog: IngredientCatalog, retry_after: int | None = None) -> FastAPI:
    repository: RecipeRepository = DownRepository()
    service = RecipeService(
        catalog=catalog, repository=repository, keys=KEYS, clock=lambda: NOW
    )
    app = create_app(catalog=catalog, service=service)
    if retry_after is not None:
        app.state.retry_after = retry_after
    return app


@pytest.mark.parametrize(("method", "path", "body"), REQUESTS)
async def test_an_unavailable_database_is_a_503_problem(
    real_catalog: IngredientCatalog,
    method: str,
    path: str,
    body: dict[str, object] | None,
) -> None:
    async with client_for(down_app(real_catalog)) as client:
        response = await client.request(method, path, json=body)

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.headers["retry-after"] == "2"
    assert response.json() == {
        "type": SERVICE_UNAVAILABLE,
        "title": "Service Unavailable",
        "status": 503,
        "detail": "We can't answer right now. Try again in a moment.",
        "request_id": response.headers["x-request-id"],
    }
    for name in SECURITY_HEADERS:
        assert name in response.headers


async def test_retry_after_comes_from_the_settings(
    real_catalog: IngredientCatalog,
) -> None:
    async with client_for(down_app(real_catalog, retry_after=7)) as client:
        response = await client.post(
            "/api/v1/recipes/search", json={"ingredient_ids": ["potato"]}
        )

    assert response.headers["retry-after"] == "7"


async def test_one_warning_names_the_cause_and_no_traceback(
    real_catalog: IngredientCatalog, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    async with client_for(down_app(real_catalog)) as client:
        response = await client.post(
            "/api/v1/recipes/search", json={"ingredient_ids": ["potato"]}
        )

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [r.getMessage() for r in warnings] == [
        "database unavailable: connection lost (57P01)"
    ]
    assert not any(r.exc_info for r in caplog.records)
    access = [r for r in caplog.records if r.name == "recipe_app.access"]
    assert access[0].__dict__["fields"]["status"] == 503
    assert response.status_code == 503


async def test_the_catalog_still_answers_while_the_database_is_down(
    real_catalog: IngredientCatalog,
) -> None:
    """Served from memory, so a pantry screen still loads (ADR-0013 rule 10)."""
    async with client_for(down_app(real_catalog)) as client:
        ingredients = await client.get("/api/v1/ingredients")
        staples = await client.get("/api/v1/staples")

    assert (ingredients.status_code, staples.status_code) == (200, 200)
