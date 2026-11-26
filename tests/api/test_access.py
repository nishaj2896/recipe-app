"""Request IDs and the access line (ADR-0013 rules 4 and 5)."""

import asyncio
import logging
import re

import pytest
from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from recipe_app.api.access import (
    REQUEST_ID_HEADER,
    RequestContext,
    log_unfinished_requests,
    new_request_id,
)
from recipe_app.api.guards import DeadlineExceededError
from recipe_app.infra.logs import REQUEST_ID
from tests.apps import AppFactory, client_for

pytestmark = pytest.mark.anyio

UUID7 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
RECIPE_ID = "01938e5c-0000-7000-8000-000000000000"


def access_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "recipe_app.access"]


def fields(record: logging.LogRecord) -> dict[str, object]:
    value = record.__dict__["fields"]
    assert isinstance(value, dict)
    return value


def test_new_ids_are_uuid7_and_sort_by_time() -> None:
    ids = [new_request_id() for _ in range(50)]

    assert all(UUID7.fullmatch(i) for i in ids)
    assert len(set(ids)) == 50
    # Within one millisecond the random tail can reorder, so compare the time.
    assert [i[:13] for i in ids] == sorted(i[:13] for i in ids)


async def test_every_response_carries_a_new_id(make_app: AppFactory) -> None:
    async with client_for(make_app()) as client:
        first = await client.get("/api/v1/ingredients")
        second = await client.get("/api/v1/nope")

    assert UUID7.fullmatch(first.headers[REQUEST_ID_HEADER])
    assert UUID7.fullmatch(second.headers[REQUEST_ID_HEADER])
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_a_valid_incoming_id_is_kept(make_app: AppFactory) -> None:
    async with client_for(make_app()) as client:
        response = await client.get(
            "/api/v1/ingredients", headers={REQUEST_ID_HEADER: "edge-1234_abcd"}
        )

    assert response.headers[REQUEST_ID_HEADER] == "edge-1234_abcd"


@pytest.mark.parametrize(
    "incoming",
    ["short", "x" * 65, "has space in it", 'quote"injection', "a/b/c/d/e/f"],
)
async def test_an_invalid_incoming_id_is_replaced(
    make_app: AppFactory, incoming: str
) -> None:
    async with client_for(make_app()) as client:
        response = await client.get(
            "/api/v1/ingredients", headers={REQUEST_ID_HEADER: incoming}
        )

    assert UUID7.fullmatch(response.headers[REQUEST_ID_HEADER])


async def test_one_access_line_with_the_route_template(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="recipe_app")
    async with client_for(make_app()) as client:
        response = await client.get(f"/api/v1/recipes/{RECIPE_ID}?token=s3cret")

    (line,) = access_lines(caplog)
    assert fields(line) == {
        "method": "GET",
        "route": "/api/v1/recipes/{recipe_id}",
        "status": response.status_code,
        "duration_ms": fields(line)["duration_ms"],
    }
    assert RECIPE_ID not in line.getMessage()
    assert "s3cret" not in caplog.text


async def test_unmatched_paths_never_log_the_path(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="recipe_app")
    async with client_for(make_app()) as client:
        await client.get("/wp-admin/evil-probe-123")

    (line,) = access_lines(caplog)
    assert fields(line)["route"] == "unmatched"
    assert fields(line)["status"] == 404
    assert "evil-probe" not in caplog.text


async def test_odd_methods_are_logged_as_other(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="recipe_app")
    async with client_for(make_app()) as client:
        await client.request("PROPFIND", "/api/v1/ingredients")

    (line,) = access_lines(caplog)
    assert fields(line)["method"] == "OTHER"


def crashing_app(make_app: AppFactory) -> FastAPI:
    app = make_app()
    seen: list[str | None] = []

    @app.get("/boom")
    async def boom() -> None:
        seen.append(REQUEST_ID.get())
        raise RuntimeError("boom")

    app.state.seen = seen
    return app


async def test_a_crash_is_logged_once_with_its_request_id(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    """The handler logs the traceback; the server must not log it again."""
    caplog.set_level(logging.INFO)
    app = crashing_app(make_app)
    async with client_for(app) as client:
        response = await client.get("/boom")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.status_code == 500
    assert response.json()["request_id"] == request_id
    assert app.state.seen == [request_id]
    tracebacks = [r for r in caplog.records if r.exc_info]
    assert len(tracebacks) == 1
    (line,) = access_lines(caplog)
    assert fields(line)["status"] == 500
    assert fields(line)["route"] == "/boom"


async def test_client_errors_have_no_request_id_in_the_body(
    make_app: AppFactory,
) -> None:
    """Only 5xx bodies carry it (ADR-0013 rule 5); the header is always there."""
    async with client_for(make_app()) as client:
        response = await client.get("/api/v1/recipes/not-a-uuid")

    assert response.status_code == 422
    assert "request_id" not in response.json()
    assert REQUEST_ID_HEADER in response.headers


async def test_the_context_is_cleared_after_the_request(make_app: AppFactory) -> None:
    async with client_for(make_app()) as client:
        await client.get("/api/v1/ingredients")

    assert REQUEST_ID.get() is None


def asgi_app(status: int) -> ASGIApp:
    """Starts a response with `status`, then fails before the body."""

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": status, "headers": []})
        raise RuntimeError("mid-body")

    return app


async def run(app: RequestContext) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": "/x", "headers": []}
    await app(scope, receive, send)
    return sent


async def test_an_error_after_a_200_still_reaches_the_server(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only the 500 that Starlette already sent is stopped (review of #128);
    a failure after any other start must be logged by the server."""
    caplog.set_level(logging.INFO, logger="recipe_app")

    with pytest.raises(RuntimeError, match="mid-body"):
        await run(RequestContext(asgi_app(200)))

    (line,) = access_lines(caplog)
    assert fields(line)["status"] == 200
    assert fields(line)["error"] == "RuntimeError"
    assert "aborted" in line.getMessage()


async def test_the_re_raise_after_a_sent_500_is_stopped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="recipe_app")

    sent = await run(RequestContext(asgi_app(500)))

    assert sent[0]["status"] == 500
    (line,) = access_lines(caplog)
    assert fields(line)["status"] == 500
    assert "error" not in fields(line)


# Cut responses (review of #131)


async def test_a_cut_response_is_logged_once_and_not_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The server then closes the connection with one line, no traceback."""
    caplog.set_level(logging.INFO, logger="recipe_app")

    async def cut(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise DeadlineExceededError

    sent = await run(RequestContext(cut))

    assert [m["type"] for m in sent] == ["http.response.start"]
    (line,) = access_lines(caplog)
    assert fields(line)["status"] == 200
    assert fields(line)["error"] == "DeadlineExceededError"
    assert "aborted" in line.getMessage()


async def test_a_request_open_at_shutdown_gets_its_line_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """uvicorn cancels a request that outlives the drain, then shuts the app
    down; the process can exit before the cancelled request unwinds."""
    caplog.set_level(logging.INFO, logger="recipe_app")
    entered = asyncio.Event()

    async def hangs(scope: Scope, receive: Receive, send: Send) -> None:
        entered.set()
        await asyncio.sleep(30)

    task = asyncio.create_task(run(RequestContext(hangs)))
    await entered.wait()
    log_unfinished_requests()
    (line,) = access_lines(caplog)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert access_lines(caplog) == [line]
    assert fields(line)["status"] is None
    assert fields(line)["error"] == "cancelled"


async def test_a_cancelled_request_is_logged_as_cancelled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="recipe_app")
    entered = asyncio.Event()

    async def hangs(scope: Scope, receive: Receive, send: Send) -> None:
        entered.set()
        await asyncio.sleep(30)

    task = asyncio.create_task(run(RequestContext(hangs)))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    (line,) = access_lines(caplog)
    assert fields(line)["error"] == "cancelled"
