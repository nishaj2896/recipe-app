"""Docs are off unless asked for, and every response carries the security headers."""

import json
from uuid import UUID

import pytest
from httpx import AsyncClient, Response

from recipe_app.api.app import create_app
from recipe_app.api.headers import API_CSP, SECURITY_HEADERS
from recipe_app.api.limits import MAX_BODY_BYTES
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.ranking import Ranking
from recipe_app.domain.recipe import Recipe
from recipe_app.services.ports import RecipeRepository
from recipe_app.services.search import RecipeService
from tests.apps import KEYS, NOW, AppFactory, client_for

pytestmark = pytest.mark.anyio

DOCS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


def assert_secured(response: Response) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get(name) == value, name


@pytest.mark.parametrize("path", DOCS)
async def test_docs_are_off_by_default(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.status_code == 404
    assert_secured(response)


@pytest.mark.parametrize("path", DOCS)
async def test_docs_are_served_when_turned_on(make_app: AppFactory, path: str) -> None:
    async with client_for(make_app(docs=True)) as client:
        response = await client.get(path)

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
async def test_docs_pages_skip_only_the_csp(make_app: AppFactory, path: str) -> None:
    """Swagger UI and ReDoc need inline script and a CDN; the rest still applies."""
    async with client_for(make_app(docs=True)) as client:
        response = await client.get(path)

    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_the_schema_itself_keeps_the_csp(make_app: AppFactory) -> None:
    async with client_for(make_app(docs=True)) as client:
        response = await client.get("/openapi.json")

    assert_secured(response)


@pytest.mark.parametrize(
    "path", ["/healthz", "/api/v1/ingredients", "/api/v1/staples", "/nope"]
)
async def test_get_responses_are_secured(client: AsyncClient, path: str) -> None:
    assert_secured(await client.get(path))


async def test_search_and_its_errors_are_secured(client: AsyncClient) -> None:
    ok = await client.post(
        "/api/v1/recipes/search", json={"ingredient_ids": ["potato"]}
    )
    invalid = await client.post("/api/v1/recipes/search", json={})
    too_large = await client.post(
        "/api/v1/recipes/search",
        content=json.dumps({"ingredient_ids": ["x" * MAX_BODY_BYTES]}),
        headers={"content-type": "application/json"},
    )

    assert (ok.status_code, invalid.status_code, too_large.status_code) == (
        200,
        422,
        413,
    )
    for response in (ok, invalid, too_large):
        assert_secured(response)


async def test_not_modified_is_secured(client: AsyncClient) -> None:
    etag = (await client.get("/api/v1/ingredients")).headers["etag"]

    response = await client.get("/api/v1/ingredients", headers={"if-none-match": etag})

    assert response.status_code == 304
    assert_secured(response)


class BrokenRepository:
    async def get(self, recipe_id: UUID) -> Recipe | None:
        raise RuntimeError("boom")

    async def ranked(self, *_: object) -> Ranking:
        raise RuntimeError("boom")


async def test_internal_errors_are_secured(real_catalog: IngredientCatalog) -> None:
    """A 500 comes from Starlette's outermost middleware, outside add_middleware."""
    repository: RecipeRepository = BrokenRepository()
    service = RecipeService(
        catalog=real_catalog, repository=repository, keys=KEYS, clock=lambda: NOW
    )
    app = create_app(catalog=real_catalog, service=service)
    async with client_for(app) as client:
        response = await client.post(
            "/api/v1/recipes/search", json={"ingredient_ids": ["potato"]}
        )

    assert response.status_code == 500
    assert_secured(response)


def test_the_api_csp_allows_nothing() -> None:
    directives = dict(d.strip().split(" ", 1) for d in API_CSP.split(";"))

    assert directives["default-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
