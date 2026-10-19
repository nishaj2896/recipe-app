"""Reading the data files; parsing and every check live in the domain.

There is no default directory: the files ship next to the code, not inside
the wheel, so the composition root passes the directory from settings.
"""

from pathlib import Path

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.recipe import Recipe, parse_recipes

CATALOG_FILE = "ingredients.v1.toml"
RECIPES_FILE = "recipes.v1.toml"


def load_catalog(data_dir: Path) -> IngredientCatalog:
    return parse_catalog((data_dir / CATALOG_FILE).read_bytes())


def load_recipes(catalog: IngredientCatalog, data_dir: Path) -> tuple[Recipe, ...]:
    return parse_recipes((data_dir / RECIPES_FILE).read_bytes(), catalog)
