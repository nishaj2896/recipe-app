from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from recipe_app.api.app import create_app
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.cursor import SigningKeys
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.services.search import RecipeService
from tests.apps import KEYS, NOW, AppFactory, client_for
from tests.domain.factories import DATA_DIR


@pytest.fixture(scope="session")
def real_catalog() -> IngredientCatalog:
    return load_catalog(DATA_DIR)


@pytest.fixture(scope="session")
def seed(real_catalog: IngredientCatalog) -> tuple[Recipe, ...]:
    return load_recipes(real_catalog, DATA_DIR)


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


@pytest.fixture
async def client(make_app: AppFactory) -> AsyncIterator[AsyncClient]:
    async with client_for(make_app()) as c:
        yield c
