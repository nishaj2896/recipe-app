import pytest

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.data import load_catalog, load_recipes
from tests.domain.factories import DATA_DIR


@pytest.fixture(scope="session")
def real_catalog() -> IngredientCatalog:
    return load_catalog(DATA_DIR)


@pytest.fixture(scope="session")
def seed(real_catalog: IngredientCatalog) -> tuple[Recipe, ...]:
    return load_recipes(real_catalog, DATA_DIR)
