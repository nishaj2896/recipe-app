"""The Task 4 gate: break the database link and the API answers a clean 503
quickly, then recovers on its own (ADR-0013 rules 1, 2 and 6).

The app is the one build_app makes for production, with short budgets (see
conftest): connect 1 s, pool wait 0.5 s, statement 0.5 s so the client budget
is 1.5 s, and a 6 s request deadline that none of these tests should reach.
"""

import asyncio

import pytest
from httpx import AsyncClient, Response

from recipe_app.api.problems import SERVICE_UNAVAILABLE
from recipe_app.domain.recipe import Recipe
from tests.chaos.proxy import ChaosProxy

pytestmark = pytest.mark.anyio

# Text of the detail page's first query: the fault lands mid-request for sure.
DETAIL_QUERY = b"WHERE recipes.id ="
CLIENT_BUDGET = 1.5
# SQLAlchemy closes a dropped connection politely for up to 2 s.
POLITE_CLOSE = 2


async def timed(client: AsyncClient, path: str) -> tuple[Response, float]:
    loop = asyncio.get_running_loop()
    started = loop.time()
    response = await client.get(path)
    return response, loop.time() - started


def assert_clean_503(response: Response) -> None:
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["retry-after"] == "2"
    body = response.json()
    assert body["type"] == SERVICE_UNAVAILABLE
    assert body["request_id"] == response.headers["x-request-id"]
    assert "Traceback" not in response.text


@pytest.fixture
def detail(seed: tuple[Recipe, ...]) -> str:
    return f"/api/v1/recipes/{seed[0].id}"


async def test_the_database_down_is_a_503_at_once_and_recovers(
    api: AsyncClient,
    proxy: ChaosProxy,
    detail: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await proxy.refuse()

    down, took = await timed(api, detail)
    catalog = await api.get("/api/v1/ingredients")
    await proxy.listen_again()
    back = await api.get(detail)

    assert_clean_503(down)
    assert took < 0.5
    assert "database unavailable: connection failed (ConnectionRefusedError)" in (
        caplog.text
    )
    # The catalog is served from memory: the deck still loads.
    assert catalog.status_code == 200
    # No restart: the next request after the database returns just works.
    assert back.status_code == 200


async def test_the_database_killed_mid_query_is_a_503_at_once(
    api: AsyncClient,
    proxy: ChaosProxy,
    detail: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    proxy.cut_on(DETAIL_QUERY)

    cut, took = await timed(api, detail)
    back = await api.get(detail)

    assert proxy.triggered.is_set()
    assert_clean_503(cut)
    assert took < 0.5
    assert "database unavailable: connection lost" in caplog.text
    # The pool threw the dead connection away and opened a new one.
    assert back.status_code == 200


async def test_a_restart_between_requests_costs_no_request(
    api: AsyncClient, proxy: ChaosProxy, detail: str
) -> None:
    """Every idle pooled connection dies; the pool's pre-ping replaces it."""
    assert (await api.get(detail)).status_code == 200
    await proxy.cut()

    assert (await api.get(detail)).status_code == 200


async def test_a_network_frozen_mid_query_ends_at_the_client_budget(
    api: AsyncClient,
    proxy: ChaosProxy,
    detail: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No reset, no reply: only asyncpg's own timer can end the wait. The
    server's statement_timeout can't help, its cancel never arrives."""
    proxy.freeze_on(DETAIL_QUERY)

    frozen, took = await timed(api, detail)
    proxy.restore()
    back = await api.get(detail)

    assert_clean_503(frozen)
    assert CLIENT_BUDGET <= took < CLIENT_BUDGET + POLITE_CLOSE + 0.5
    assert "database unavailable: statement timeout (client)" in caplog.text
    assert "request deadline" not in caplog.text
    assert back.status_code == 200


async def test_a_network_frozen_before_the_request_is_a_503(
    api: AsyncClient,
    proxy: ChaosProxy,
    detail: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The pooled connection fails its pre-ping: no working connection."""
    assert (await api.get(detail)).status_code == 200
    proxy.freeze()

    frozen, took = await timed(api, detail)
    proxy.restore()
    back = await api.get(detail)

    assert_clean_503(frozen)
    assert took < CLIENT_BUDGET + POLITE_CLOSE + 0.5
    assert "database unavailable: connect timeout" in caplog.text
    assert back.status_code == 200


async def test_one_stuck_query_stalls_others_only_for_the_pool_wait(
    api: AsyncClient,
    proxy: ChaosProxy,
    detail: str,
    seed: tuple[Recipe, ...],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The pool holds one connection here; the stuck request holds it."""
    proxy.freeze_on(DETAIL_QUERY)
    stuck = asyncio.create_task(api.get(detail))
    await asyncio.wait_for(proxy.triggered.wait(), timeout=2)

    waiting, took = await timed(api, f"/api/v1/recipes/{seed[1].id}")
    proxy.restore()
    await stuck

    assert_clean_503(waiting)
    # The 0.5 s pool wait, with room for a loaded CI runner.
    assert 0.5 <= took < 2
    assert "database unavailable: pool timeout" in caplog.text
