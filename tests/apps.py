"""Building the app for HTTP tests: shared by tests/api and tests/contract."""

from collections.abc import Callable

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from recipe_app.domain.cursor import SigningKeys

KEYS = SigningKeys(active_kid="test", keys={"test": b"k" * 32})
NOW = 1_800_000_000

type AppFactory = Callable[..., FastAPI]


def client_for(app: FastAPI) -> AsyncClient:
    # raise_app_exceptions=False: a crash must come back as the 500 a real
    # client sees, not as an exception in the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")
