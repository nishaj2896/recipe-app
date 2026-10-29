"""Reading the data files; parsing and every check live in the domain.

There is no default directory: the files ship next to the code, not inside
the wheel, so `recipe-app db sync` passes the directory from settings. The
server itself reads the database, not these files (ADR-0005 rule 1).
"""

from pathlib import Path

from recipe_app.domain.book import RecipeBook, parse_recipe_book
from recipe_app.domain.catalog import IngredientCatalog, parse_catalog
from recipe_app.domain.recipe import Recipe

CATALOG_FILE = "ingredients.v1.toml"
# Every *.toml file in it, read in name order (ADR-0008 rule 3).
RECIPES_DIR = "recipes"


def load_catalog(data_dir: Path) -> IngredientCatalog:
    return parse_catalog((data_dir / CATALOG_FILE).read_bytes())


def load_recipe_book(catalog: IngredientCatalog, data_dir: Path) -> RecipeBook:
    directory = data_dir / RECIPES_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"no recipe directory at {directory}")
    files = sorted(directory.glob("*.toml"))
    return parse_recipe_book(
        [(path.name, path.read_bytes()) for path in files], catalog
    )


def load_recipes(catalog: IngredientCatalog, data_dir: Path) -> tuple[Recipe, ...]:
    return load_recipe_book(catalog, data_dir).recipes
