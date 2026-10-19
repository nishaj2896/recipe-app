import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from recipe_app.api.problems import (
    CURSOR_EXPIRED,
    INVALID_CURSOR,
    MAX_ERRORS,
    PROBLEM_MEDIA_TYPE,
    field_path,
)
from recipe_app.domain.cursor import SigningKeys
from tests.apps import NOW, AppFactory, client_for

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("loc", "expected"),
    [
        pytest.param(("body", "ingredient_ids", 0), "ingredient_ids[0]", id="item"),
        pytest.param(("body", "evil"), "evil", id="field"),
        pytest.param(("path", "recipe_id"), "recipe_id", id="path"),
        pytest.param(("body",), "body", id="whole-body"),
        pytest.param(("body", "a", 2, "b"), "a[2].b", id="nested"),
        pytest.param(("body", "<b>"), "body", id="unsafe-name"),
        pytest.param(("body", "x" * 65), "body", id="long-name"),
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


SEARCH = "/api/v1/recipes/search"


def assert_problem(response: Response, status: int, problem_type: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json()["type"] == problem_type


async def a_cursor(client: AsyncClient, **body: object) -> str:
    response = await client.post(SEARCH, json={"ingredient_ids": ["potato"]} | body)
    cursor: str = response.json()["next_cursor"]
    assert cursor
    return cursor


@pytest.mark.parametrize(
    ("cursor", "body"),
    [
        pytest.param("x" * 1025, {}, id="too-long"),
        pytest.param("junk", {}, id="malformed"),
        pytest.param(None, {"diet": "vegan"}, id="other-filters"),
        pytest.param(None, {"tamper": True}, id="tampered"),
    ],
)
async def test_invalid_cursor_problem(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    cursor: str | None,
    body: dict[str, object],
) -> None:
    """ADR-0003 rule 9: every invalid cursor is logged, wherever it is rejected."""
    if cursor is None:
        cursor = await a_cursor(client)
        if body.pop("tamper", False):
            cursor = cursor[:-2] + ("AA" if cursor[-2:] != "AA" else "BB")
    response = await client.post(
        SEARCH, json={"ingredient_ids": ["potato"], "cursor": cursor} | body
    )

    assert_problem(response, 422, INVALID_CURSOR)
    assert "errors" not in response.json()
    assert "invalid cursor" in caplog.text


async def test_expired_cursor_problem_when_old_or_key_removed(
    make_app: AppFactory,
) -> None:
    async with client_for(make_app()) as client:
        cursor = await a_cursor(client)
    later = make_app(now=NOW + 86_401)
    rotated = make_app(keys=SigningKeys(active_kid="new", keys={"new": b"n" * 32}))
    body = {"ingredient_ids": ["potato"], "cursor": cursor}

    for app in (later, rotated):
        async with client_for(app) as client:
            assert_problem(await client.post(SEARCH, json=body), 422, CURSOR_EXPIRED)


async def test_unpublished_id_names_the_field(client: AsyncClient) -> None:
    response = await client.post(SEARCH, json={"ingredient_ids": ["unobtainium"]})

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"] == [
        {"field": "ingredient_ids", "message": "unknown ingredient 'unobtainium'"}
    ]


async def test_unknown_recipe_problem(client: AsyncClient) -> None:
    missing = "019a0c3e-8f00-7a1b-9c2d-3e4f5a6b7c8d"
    response = await client.get(f"/api/v1/recipes/{missing}")

    assert_problem(response, 404, "about:blank")
    assert response.json()["title"] == "Recipe not found"


async def test_errors_are_capped_but_counted(client: AsyncClient) -> None:
    body: dict[str, object] = {"ingredient_ids": ["potato"]}
    body |= {f"extra_{n}": n for n in range(1_000)}

    response = await client.post(SEARCH, json=body)

    assert_problem(response, 422, "about:blank")
    assert len(response.json()["errors"]) == MAX_ERRORS
    assert response.json()["detail"].startswith("1000 fields failed validation.")
    assert len(response.content) < 4_096


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(
            b'{"ingredient_ids": ["potato"], "<script>x</script>": 1}',
            {"field": "body", "message": "Extra inputs are not permitted"},
            id="unknown-key",
        ),
        pytest.param(
            b'{"ingredient_ids": [',
            {"field": "body", "message": "Request body is not valid JSON"},
            id="bad-json",
        ),
        pytest.param(
            b'{"ingredient_ids": ["potato"], "hidden_recipe_ids": ["nope-secret"]}',
            {
                "field": "hidden_recipe_ids[0]",
                "message": "Input should be a valid UUID",
            },
            id="bad-uuid",
        ),
    ],
)
async def test_errors_never_echo_the_input(
    client: AsyncClient, body: bytes, expected: dict[str, str]
) -> None:
    response = await client.post(
        SEARCH, content=body, headers={"content-type": "application/json"}
    )

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"] == [expected]
    for leaked in ("script", "nope", "secret"):
        assert leaked not in response.text
