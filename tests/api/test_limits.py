import json
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from recipe_app.api.limits import MAX_BODY_BYTES
from recipe_app.api.problems import PROBLEM_MEDIA_TYPE

pytestmark = pytest.mark.anyio

SEARCH = "/api/v1/recipes/search"
JSON_HEADERS = {"content-type": "application/json"}


def _too_large(body: bytes) -> bool:
    return len(body) > MAX_BODY_BYTES


async def test_declared_oversized_body_is_413(client: AsyncClient) -> None:
    body = json.dumps({"ingredient_ids": ["potato"], "cursor": "a" * MAX_BODY_BYTES})
    assert _too_large(body.encode())

    response = await client.post(SEARCH, content=body, headers=JSON_HEADERS)

    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["status"] == 413


async def test_streamed_oversized_body_without_length_is_413(
    client: AsyncClient,
) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"ingredient_ids": ["potato"], "cursor": "'
        for _ in range(MAX_BODY_BYTES // 1024 + 1):
            yield b"a" * 1024
        yield b'"}'

    response = await client.post(SEARCH, content=chunks(), headers=JSON_HEADERS)

    assert response.status_code == 413


async def test_largest_valid_search_fits_under_the_cap(client: AsyncClient) -> None:
    # Every list at its maximum with the longest ids: still far below the cap.
    body = json.dumps(
        {
            "ingredient_ids": [f"{i:02d}" + "x" * 62 for i in range(50)],
            "excluded_staples": [f"{i:03d}" + "y" * 61 for i in range(100)],
            "hidden_recipe_ids": [str(uuid.uuid4()) for _ in range(200)],
            "cursor": "c" * 1024,
        }
    ).encode()
    assert not _too_large(body)

    response = await client.post(SEARCH, content=body, headers=JSON_HEADERS)

    # Rejected for its made-up ids, which proves the body reached validation.
    assert response.status_code == 422


async def test_body_under_the_cap_still_searches(client: AsyncClient) -> None:
    response = await client.post(SEARCH, json={"ingredient_ids": ["potato"]})

    assert response.status_code == 200
