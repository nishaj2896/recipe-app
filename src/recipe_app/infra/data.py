"""Reading the checked-in data files; parsing and every check live in the domain."""

from pathlib import Path

from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.recipe import Recipe, parse_recipes

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CATALOG_FILE = "ingredients.v1.toml"
RECIPES_FILE = "recipes.v1.toml"


def load_catalog(data_dir: Path = DATA_DIR) -> IngredientCatalog:
    return parse_catalog((data_dir / CATALOG_FILE).read_bytes())


def load_recipes(
    catalog: IngredientCatalog, data_dir: Path = DATA_DIR
) -> tuple[Recipe, ...]:
    return parse_recipes((data_dir / RECIPES_FILE).read_bytes(), catalog)
