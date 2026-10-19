import pytest

from recipe_app.domain.recipe import Recipe
from recipe_app.infra.memory import InMemoryRecipeRepository


def test_duplicate_recipe_id_is_rejected(seed: tuple[Recipe, ...]) -> None:
    with pytest.raises(ValueError, match="duplicate recipe id"):
        InMemoryRecipeRepository([seed[0], seed[0]])
