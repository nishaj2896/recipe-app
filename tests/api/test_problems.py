import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from recipe_app.api.problems import PROBLEM_MEDIA_TYPE, field_path
from tests.api.conftest import AppFactory, client_for

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        pytest.param(("body", "ingredient_ids", 0), "ingredient_ids[0]", id="item"),
        pytest.param(("body", "evil"), "evil", id="field"),
        pytest.param(("path", "recipe_id"), "recipe_id", id="path"),
        pytest.param(("body",), "body", id="whole-body"),
        pytest.param(("body", "a", 2, "b"), "a[2].b", id="nested"),
    ],
)
def test_field_path(loc: tuple[int | str, ...], expected: str) -> None:
    assert field_path(loc) == expected


def crashing_app(make_app: AppFactory) -> FastAPI:
    app = make_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail: /etc/passwd at line 42")

    return app


async def test_crash_is_a_generic_500_without_a_traceback(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    async with client_for(crashing_app(make_app)) as client:
        with caplog.at_level(logging.ERROR):
            response = await client.get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json() == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "detail": "Something went wrong on our side. Try again later.",
    }
    assert "secret" not in response.text
    assert "Traceback" not in response.text
    # The detail goes to the log instead, where an operator can find it.
    assert "secret detail" in caplog.text


async def test_invalid_json_is_a_problem(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/recipes/search",
        content=b'{"ingredient_ids": [',
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["title"] == "Invalid request"


async def test_validation_messages_never_echo_the_input(client: AsyncClient) -> None:
    secret = "x" * 65
    response = await client.post(
        "/api/v1/recipes/search", json={"ingredient_ids": [secret]}
    )

    assert response.status_code == 422
    assert secret not in response.text
