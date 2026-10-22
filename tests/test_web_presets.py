"""The web app's ingredient lists and art registry match the catalog.

A typo or a retired id in a ready-made list would be sent in `ingredient_ids`
and fail the search with a 422, and a category with no art falls back to a
generic drawing. These check web/src/pantry/presets.json and
web/src/art/registry.json against the catalog the API serves.
"""

import json
from pathlib import Path

import pytest

from recipe_app.domain.catalog import IngredientCatalog, IngredientClass

WEB_SRC = Path(__file__).parents[1] / "web" / "src"


def _preset_lists() -> list[tuple[str, list[str]]]:
    presets = json.loads((WEB_SRC / "pantry" / "presets.json").read_text())
    lists = [("popular", presets["popular"])]
    lists += [(item["id"], item["ingredient_ids"]) for item in presets["quick_starts"]]
    return lists


@pytest.mark.parametrize(("name", "ids"), _preset_lists())
def test_preset_names_only_pickable_ingredients(
    name: str, ids: list[str], real_catalog: IngredientCatalog
) -> None:
    pickable = {
        item.id
        for item in real_catalog.by_id.values()
        if not item.retired and item.ingredient_class is not IngredientClass.STAPLE
    }
    assert [i for i in ids if i not in pickable] == [], name
    assert len(ids) == len(set(ids)), f"{name} lists an id twice"


def test_art_registry_names_only_catalog_ingredients(
    real_catalog: IngredientCatalog,
) -> None:
    registry = json.loads((WEB_SRC / "art" / "registry.json").read_text())
    assert [i for i in registry["ingredients"] if i not in real_catalog.by_id] == []


def test_every_catalog_category_has_art(real_catalog: IngredientCatalog) -> None:
    registry = json.loads((WEB_SRC / "art" / "registry.json").read_text())
    categories = {item.category for item in real_catalog.by_id.values()}
    assert sorted(categories - registry["categories"].keys()) == []


def test_every_own_drawing_is_a_catalog_ingredient(
    real_catalog: IngredientCatalog,
) -> None:
    listed = json.loads((WEB_SRC / "art" / "own.json").read_text())
    assert sorted(set(listed) - real_catalog.by_id.keys()) == []
