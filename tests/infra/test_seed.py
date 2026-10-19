"""The checked-in data files load with the startup checks (ADR-0002 rule 7)."""

from collections import Counter
from pathlib import Path

import pytest

from recipe_app.domain.catalog import Diet, IngredientCatalog, IngredientClass
from recipe_app.domain.recipe import Recipe
from recipe_app.infra.data import load_catalog, load_recipes


def test_seed_file_loads(seed: tuple[Recipe, ...]) -> None:
    assert len(seed) >= 40


def test_seed_covers_every_diet(seed: tuple[Recipe, ...]) -> None:
    assert set(Counter(recipe.diet for recipe in seed)) == set(Diet)


def test_seed_has_all_staples_recipes(seed: tuple[Recipe, ...]) -> None:
    """The all-staples tier needs real cards for the demo and the gate."""
    all_staples = [
        recipe
        for recipe in seed
        if all(i.ingredient_class is IngredientClass.STAPLE for i in recipe.ingredients)
    ]

    assert len(all_staples) >= 2


def test_missing_data_directory_names_the_file(
    tmp_path: Path, real_catalog: IngredientCatalog
) -> None:
    """An install without the data files fails loudly at startup, not on a search."""
    with pytest.raises(FileNotFoundError, match=r"ingredients\.v1\.toml"):
        load_catalog(tmp_path)
    with pytest.raises(FileNotFoundError, match=r"recipes\.v1\.toml"):
        load_recipes(real_catalog, tmp_path)
