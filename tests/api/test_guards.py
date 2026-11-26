"""The request deadline and the concurrency limit (ADR-0013 rule 7)."""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from starlette.types import Message, Receive, Scope, Send

from recipe_app.api.guards import (
    ConcurrencyLimit,
    DeadlineExceededError,
    Guards,
    RequestDeadline,
)
from recipe_app.api.problems import SERVICE_UNAVAILABLE
from recipe_app.infra.database import EngineLimits, create_engine
from tests.apps import AppFactory, client_for

pytestmark = pytest.mark.anyio


def with_slow_route(app: FastAPI, seconds: float) -> FastAPI:
    @app.get("/slow")
    async def slow() -> dict[str, str]:
        await asyncio.sleep(seconds)
        return {"done": "yes"}

    return app


async def test_a_request_past_its_deadline_is_a_503(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    app = with_slow_route(make_app(guards=Guards(request_timeout=0.1)), seconds=5)
    loop = asyncio.get_running_loop()
    async with client_for(app) as client:
        started = loop.time()
        response = await client.get("/slow")
        took = loop.time() - started

    assert response.status_code == 503
    assert response.json()["type"] == SERVICE_UNAVAILABLE
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.headers["retry-after"] == "2"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert took < 1
    assert "request deadline of 0.1s exceeded" in caplog.text


async def test_a_fast_request_is_untouched(make_app: AppFactory) -> None:
    app = with_slow_route(make_app(guards=Guards(request_timeout=1)), seconds=0)
    async with client_for(app) as client:
        response = await client.get("/slow")

    assert response.status_code == 200


# The middleware on its own


def scope_for(path: str) -> Scope:
    return {"type": "http", "method": "GET", "path": path, "headers": []}


async def call(app: object, path: str = "/x") -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope_for(path), receive, send)  # type: ignore[operator]
    return sent


async def starts_then_hangs(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await asyncio.sleep(5)


async def hangs(scope: Scope, receive: Receive, send: Send) -> None:
    await asyncio.sleep(5)


async def raises_its_own_timeout(scope: Scope, receive: Receive, send: Send) -> None:
    raise TimeoutError("the app's own")


async def test_after_the_response_started_the_connection_is_cut() -> None:
    """No 503 can follow a 200 status line; the server drops the connection."""
    with pytest.raises(DeadlineExceededError):
        await call(RequestDeadline(starts_then_hangs, 0.05, retry_after=2))


async def test_the_apps_own_timeout_is_not_the_deadline() -> None:
    with pytest.raises(TimeoutError, match="the app's own"):
        await call(RequestDeadline(raises_its_own_timeout, 5, retry_after=2))


async def test_liveness_has_no_deadline() -> None:
    async def slowish(scope: Scope, receive: Receive, send: Send) -> None:
        await asyncio.sleep(0.1)
        await send({"type": "http.response.start", "status": 200, "headers": []})

    sent = await call(RequestDeadline(slowish, 0.01, retry_after=2), "/healthz")

    assert sent[0]["status"] == 200


async def test_the_deadline_answers_503_before_any_response() -> None:
    sent = await call(RequestDeadline(hangs, 0.05, retry_after=9))

    assert sent[0]["status"] == 503
    assert (b"retry-after", b"9") in sent[0]["headers"]


# The concurrency limit


async def test_one_request_too_many_is_shed_at_once(
    make_app: AppFactory, caplog: pytest.LogCaptureFixture
) -> None:
    release = asyncio.Event()
    app = make_app(guards=Guards(max_in_flight=2))

    @app.get("/wait")
    async def wait() -> dict[str, str]:
        await release.wait()
        return {"done": "yes"}

    async with client_for(app) as client:
        held = [asyncio.create_task(client.get("/wait")) for _ in range(2)]
        await asyncio.sleep(0.05)
        shed = await asyncio.wait_for(client.get("/wait"), timeout=1)
        alive = await client.get("/healthz")
        release.set()
        finished = await asyncio.gather(*held)
        after = await client.get("/api/v1/ingredients")

    assert shed.status_code == 503
    assert shed.json()["type"] == SERVICE_UNAVAILABLE
    assert alive.status_code == 200
    assert [r.status_code for r in finished] == [200, 200]
    assert after.status_code == 200
    assert "2 requests already in flight; shedding" in caplog.text


async def test_the_count_goes_down_when_a_request_fails() -> None:
    async def boom(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("boom")

    limit = ConcurrencyLimit(boom, limit=1, retry_after=2)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await call(limit)

    assert limit.in_flight == 0


# A deadline that fires mid-query (review of #126)


async def test_a_query_cut_by_the_deadline_leaves_a_working_pool(
    make_app: AppFactory, migrated_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    engine = create_engine(
        migrated_database_url, EngineLimits(pool_size=1, max_overflow=0)
    )
    app = make_app(guards=Guards(request_timeout=0.3))

    @app.get("/query/{seconds}")
    async def query(seconds: float) -> dict[str, object]:
        async with engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT 1 FROM pg_sleep(:seconds)"), {"seconds": seconds}
            )
        return {"value": value}

    try:
        async with client_for(app) as client:
            cut = await client.get("/query/2.5")
            # The pool holds one connection; the cut one must not come back
            # broken, or this request would fail.
            after = await client.get("/query/0")

        async with engine.connect() as connection:
            running = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE query LIKE 'SELECT 1 FROM pg_sleep(%' AND state = 'active'"
                )
            )
    finally:
        await engine.dispose()

    assert cut.status_code == 503
    assert after.status_code == 200
    assert after.json() == {"value": 1}
    # The server stopped the query too, not only the client.
    assert running == 0
