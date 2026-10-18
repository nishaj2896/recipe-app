import json
import re
from pathlib import Path

import pytest

from recipe_app.domain.catalog import CatalogError, IngredientCatalog, parse_catalog

DATA_FILE = Path(__file__).parents[2] / "data" / "ingredients.v1.toml"


def test_real_catalog_file_loads() -> None:
    catalog = parse_catalog(DATA_FILE.read_bytes())

    assert isinstance(catalog, IngredientCatalog)
    assert "potato" in catalog.by_id


CATEGORY = '[[category]]\nid = "vegetables"\nname = "Vegetables"\nposition = 10\n'


def category(**fields: object) -> str:
    """A valid [[category]] table for vegetables. Override fields; None drops one."""
    row: dict[str, object] = {
        "id": "vegetables",
        "name": "Vegetables",
        "position": 10,
    } | fields
    lines = [
        f"{key} = {json.dumps(value)}"
        for key, value in row.items()
        if value is not None
    ]
    return "[[category]]\n" + "\n".join(lines) + "\n"


def ingredient(**fields: object) -> str:
    """A valid [[ingredient]] table for potato. Override fields; None drops one."""
    row: dict[str, object] = {
        "id": "potato",
        "name": "Potato",
        "class": "A",
        "diet": "vegan",
        "category": "vegetables",
    } | fields
    lines = [
        f"{key} = {json.dumps(value)}"
        for key, value in row.items()
        if value is not None
    ]
    return "[[ingredient]]\n" + "\n".join(lines) + "\n"


def catalog(*tables: str) -> bytes:
    return "\n".join(tables).encode()


def test_minimal_catalog_is_valid() -> None:
    assert "potato" in parse_catalog(catalog(CATEGORY, ingredient())).by_id


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        pytest.param(b"", "empty", id="empty-file"),
        # Ingredient rules: one changed field
        pytest.param(
            catalog(category(), ingredient(id="Potato!")),
            "id 'Potato!' is not a slug",
            id="id-not-a-slug",
        ),
        pytest.param(
            b'ingredient = [{ id = "potato", name = "Potato", class = "A", '
            b'diet = "vegan", category = "vegetables" }, "leek"]\n'
            + catalog(category()),
            "ingredient #2 is not a table",
            id="entry-not-a-table",
        ),
        pytest.param(
            catalog(category(), ingredient(name=" Potato  ")),
            "name ' Potato  ' has extra whitespace",
            id="name-with-extra-whitespace",
        ),
        pytest.param(
            catalog(category(), ingredient(id="a" * 65)),
            "is longer than 64 characters",
            id="id-too-long",
        ),
        pytest.param(
            catalog(category(), ingredient(**{"class": "X"})),
            "unknown class 'X'",
            id="unknown-class",
        ),
        pytest.param(
            catalog(category(), ingredient(**{"class": "S"}, kind="frozen")),
            "unknown kind 'frozen'",
            id="unknown-kind",
        ),
        pytest.param(
            catalog(category(), ingredient(diet="meat")),
            "unknown diet 'meat'",
            id="unknown-diet",
        ),
        pytest.param(
            catalog(
                category(),
                ingredient(),
                ingredient(id="leek", name="Leek", category="veg"),
            ),
            "unknown category 'veg'",
            id="unknown-category",
        ),
        pytest.param(
            catalog(category(), ingredient(kind="pantry")),
            "only class S can have a kind",
            id="kind-on-class-a",
        ),
        pytest.param(
            catalog(category(), ingredient(**{"class": "S"})),
            "class S needs a kind",
            id="class-s-without-kind",
        ),
        pytest.param(
            catalog(category(), ingredient(retierd=True)),
            "unknown field 'retierd'",
            id="unknown-field",
        ),
        pytest.param(
            catalog(
                category(),
                ingredient(),
                ingredient(id="milk", name="Milk", **{"class": "S"}, kind="fresh"),
            ),
            "'milk' can never be a staple",
            id="never-staple",
        ),
        # Ingredient rules: a second ingredient that clashes
        pytest.param(
            catalog(category(), ingredient(), ingredient(name="Potato 2")),
            "duplicate id 'potato'",
            id="duplicate-id",
        ),
        pytest.param(
            catalog(
                category(),
                ingredient(),
                ingredient(id="potato-2", name=" POTATO "),
            ),
            "duplicate name 'potato'",
            id="duplicate-normalized-name",
        ),
        # Category rules: change the category
        pytest.param(
            catalog(category(retired=True), ingredient()),
            "uses retired category 'vegetables'",
            id="live-ingredient-in-retired-category",
        ),
        pytest.param(
            catalog(category(name="Fresh  vegetables"), ingredient()),
            "name 'Fresh  vegetables' has extra whitespace",
            id="category-name-with-extra-whitespace",
        ),
        pytest.param(
            catalog(category(position=0), ingredient()),
            "position must be a positive integer",
            id="position-zero",
        ),
        # Category rules: a second category that clashes
        pytest.param(
            catalog(category(), category(name="Fruits", position=20), ingredient()),
            "duplicate category id 'vegetables'",
            id="duplicate-category-id",
        ),
        pytest.param(
            catalog(
                category(),
                category(id="greens", name=" VEGETABLES ", position=20),
                ingredient(),
                ingredient(id="spinach", name="Spinach", category="greens"),
            ),
            "duplicate category name 'vegetables'",
            id="duplicate-category-name",
        ),
        pytest.param(
            catalog(
                category(),
                category(id="fruits", name="Fruits"),
                ingredient(),
                ingredient(id="apple", name="Apple", category="fruits"),
            ),
            "duplicate category position 10",
            id="duplicate-category-position",
        ),
        pytest.param(
            catalog(
                category(),
                category(id="fruits", name="Fruits", position=20),
                ingredient(),
            ),
            "category 'fruits' has no live ingredients",
            id="empty-category",
        ),
    ],
)
def test_rejects(raw: bytes, message: str) -> None:
    with pytest.raises(CatalogError, match=re.escape(message)):
        parse_catalog(raw)
