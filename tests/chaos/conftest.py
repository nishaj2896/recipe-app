import base64
import json
from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy.engine import make_url

from recipe_app.api.app import build_app
from tests.apps import client_for
from tests.chaos.proxy import ChaosProxy

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()


@pytest.fixture
async def proxy(seeded_database_url: str) -> AsyncIterator[ChaosProxy]:
    """The seeded database, reached through a proxy the test can break."""
    url = make_url(seeded_database_url)
    chaos = ChaosProxy(url.host or "localhost", url.port or 5432)
    await chaos.start()
    try:
        yield chaos
    finally:
        await chaos.close()


@pytest.fixture
def api_env(
    monkeypatch: pytest.MonkeyPatch, proxy: ChaosProxy, seeded_database_url: str
) -> pytest.MonkeyPatch:
    """The settings production reads, pointed at the proxy, with short budgets
    so a test waits seconds, not the production defaults."""
    for name, value in {
        "DATABASE_URL": proxy.url(seeded_database_url),
        "CURSOR_SIGNING_KEYS": json.dumps({"a": KEY}),
        "CURSOR_ACTIVE_KID": "a",
        "DATABASE_CONNECT_TIMEOUT_SECONDS": "1",
        "DATABASE_POOL_TIMEOUT_SECONDS": "0.5",
        "DATABASE_STATEMENT_TIMEOUT_SECONDS": "0.5",
        "DATABASE_POOL_SIZE": "1",
        "DATABASE_POOL_MAX_OVERFLOW": "0",
        "REQUEST_TIMEOUT_SECONDS": "6",
        "LOG_FORMAT": "json",
    }.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


@pytest.fixture
async def api(
    api_env: pytest.MonkeyPatch, bare_app_logger: object
) -> AsyncIterator[AsyncClient]:
    """The app as build_app makes it for production, lifespan and all."""
    app = build_app()
    async with app.router.lifespan_context(app), client_for(app) as client:
        yield client
