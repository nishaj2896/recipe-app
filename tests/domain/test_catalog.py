import hashlib
import re

import pytest

from recipe_app.domain.catalog import (
    CatalogError,
    Diet,
    IngredientCatalog,
    parse_catalog,
)
from tests.domain.factories import DATA_FILE, catalog, category, ingredient


def test_real_catalog_file_loads() -> None:
    catalog = parse_catalog(DATA_FILE.read_bytes())

    assert isinstance(catalog, IngredientCatalog)
    assert "potato" in catalog.by_id


def test_minimal_catalog_is_valid() -> None:
    assert "potato" in parse_catalog(catalog(category(), ingredient())).by_id


def test_reports_every_problem_at_once() -> None:
    raw = catalog(category(), ingredient(diet="meat", retierd=True))

    with pytest.raises(CatalogError) as caught:
        parse_catalog(raw)

    assert len(caught.value.problems) == 2


def test_retired_ingredient_may_stay_in_retired_category() -> None:
    raw = catalog(
        category(),
        category(id="old", name="Old", position=20, retired=True),
        ingredient(),
        ingredient(id="leek", name="Leek", category="old", retired=True),
    )

    assert parse_catalog(raw).by_id["leek"].retired


def test_content_hash_is_sha256_of_the_file() -> None:
    raw = catalog(category(), ingredient())

    assert parse_catalog(raw).content_hash == hashlib.sha256(raw).hexdigest()


def test_search_terms_are_stored_normalized() -> None:
    raw = catalog(category(), ingredient(search_terms=["  Baby  POTATO "]))

    assert parse_catalog(raw).by_id["potato"].search_terms == ("baby potato",)


def test_invalid_values_are_not_reported_as_duplicates() -> None:
    raw = catalog(
        category(id=None),
        category(id=None, name="Fruits", position=0),
        category(id="greens", name="Greens", position=0),
        ingredient(id=None),
        ingredient(id=None, name=None),
        ingredient(id="leek", name=None),
    )

    with pytest.raises(CatalogError) as caught:
        parse_catalog(raw)

    assert not [p for p in caught.value.problems if "duplicate" in p]


@pytest.mark.parametrize(
    ("requested", "recipe_diet", "expected"),
    [
        pytest.param(Diet.VEGAN, Diet.VEGAN, True, id="vegan-sees-vegan"),
        pytest.param(Diet.VEGAN, Diet.VEGETARIAN, False, id="vegan-hides-vegetarian"),
        pytest.param(Diet.VEGAN, Diet.EGG, False, id="vegan-hides-egg"),
        pytest.param(Diet.VEGAN, Diet.NON_VEG, False, id="vegan-hides-non-veg"),
        pytest.param(Diet.VEGETARIAN, Diet.VEGAN, True, id="vegetarian-sees-vegan"),
        pytest.param(
            Diet.VEGETARIAN, Diet.VEGETARIAN, True, id="vegetarian-sees-vegetarian"
        ),
        pytest.param(Diet.VEGETARIAN, Diet.EGG, False, id="vegetarian-hides-egg"),
        pytest.param(
            Diet.VEGETARIAN, Diet.NON_VEG, False, id="vegetarian-hides-non-veg"
        ),
        pytest.param(Diet.EGG, Diet.VEGAN, True, id="egg-sees-vegan"),
        pytest.param(Diet.EGG, Diet.VEGETARIAN, True, id="egg-sees-vegetarian"),
        pytest.param(Diet.EGG, Diet.EGG, True, id="egg-sees-egg"),
        pytest.param(Diet.EGG, Diet.NON_VEG, False, id="egg-hides-non-veg"),
        pytest.param(Diet.NON_VEG, Diet.VEGAN, True, id="non-veg-sees-vegan"),
        pytest.param(Diet.NON_VEG, Diet.VEGETARIAN, True, id="non-veg-sees-vegetarian"),
        pytest.param(Diet.NON_VEG, Diet.EGG, True, id="non-veg-sees-egg"),
        pytest.param(Diet.NON_VEG, Diet.NON_VEG, True, id="non-veg-sees-non-veg"),
    ],
)
def test_diet_allows(requested: Diet, recipe_diet: Diet, expected: bool) -> None:
    assert requested.allows(recipe_diet) is expected


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
                ingredient(id="potato-2", name="POTATO"),
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
                category(id="greens", name="VEGETABLES", position=20),
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
