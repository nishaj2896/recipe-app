from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from recipe_app.api.app import create_app
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.cursor import SigningKeys
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.services.search import RecipeService

KEYS = SigningKeys(active_kid="test", keys={"test": b"k" * 32})
NOW = 1_800_000_000

type AppFactory = Callable[..., FastAPI]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def make_app(real_catalog: IngredientCatalog, seed: tuple[Recipe, ...]) -> AppFactory:
    """An app over the real catalog; pass recipes, keys or a clock to change one."""

    def make(
        *,
        recipes: tuple[Recipe, ...] = seed,
        catalog: IngredientCatalog = real_catalog,
        keys: SigningKeys = KEYS,
        now: int = NOW,
    ) -> FastAPI:
        service = RecipeService(
            catalog=catalog,
            repository=InMemoryRecipeRepository(recipes),
            keys=keys,
            clock=lambda: now,
        )
        return create_app(catalog=catalog, service=service)

    return make


def client_for(app: FastAPI) -> AsyncClient:
    # raise_app_exceptions=False: a crash must come back as the 500 a real
    # client sees, not as an exception in the test.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def client(make_app: AppFactory) -> AsyncIterator[AsyncClient]:
    async with client_for(make_app()) as c:
        yield c
