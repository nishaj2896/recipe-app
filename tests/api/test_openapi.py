from typing import Any

import pytest
from httpx import AsyncClient

from recipe_app.api.problems import PROBLEM_MEDIA_TYPE

pytestmark = pytest.mark.anyio


async def test_every_error_response_is_a_problem(client: AsyncClient) -> None:
    schema: dict[str, Any] = (await client.get("/openapi.json")).json()

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            for status, response in operation["responses"].items():
                if status[0] not in "45":
                    continue
                assert set(response["content"]) == {PROBLEM_MEDIA_TYPE}, (
                    f"{method} {path} {status}"
                )
                assert response["content"][PROBLEM_MEDIA_TYPE]["schema"] == {
                    "$ref": "#/components/schemas/Problem"
                }, f"{method} {path} {status}"
            assert "500" in operation["responses"], f"{method} {path}"
    assert "HTTPValidationError" not in schema["components"]["schemas"]


async def test_catalog_routes_document_if_none_match(client: AsyncClient) -> None:
    schema: dict[str, Any] = (await client.get("/openapi.json")).json()

    for path in ("/api/v1/ingredients", "/api/v1/staples"):
        operation = schema["paths"][path]["get"]
        assert [p["name"] for p in operation["parameters"]] == ["If-None-Match"]
        assert "304" in operation["responses"]
