import pytest

from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.memory import InMemoryRecipeRepository


def test_duplicate_recipe_id_is_rejected() -> None:
    seed = load_recipes(load_catalog())

    with pytest.raises(ValueError, match="duplicate recipe id"):
        InMemoryRecipeRepository([seed[0], seed[0]])
