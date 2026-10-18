from collections.abc import Sequence
from uuid import UUID

import pytest

from recipe_app.domain.catalog import Ingredient, parse_catalog
from recipe_app.domain.matching import (
    AllStaplesMatch,
    ScoredMatch,
    match_recipe,
    resolve_pantry,
)
from recipe_app.domain.recipe import Recipe, build_recipe
from tests.domain.factories import DATA_FILE

# ADR-0003 names real ingredients, so these tests use the real catalog.
CATALOG = parse_catalog(DATA_FILE.read_bytes())

ALOO_MATAR = ["potato", "peas", "tomato", "onion", "turmeric", "salt", "ghee"]
KHEER = ["rice", "milk", "sugar"]
TOMATO_SOUP = ["tomato", "onion", "garlic", "butter", "salt"]


def recipe(ingredient_ids: Sequence[str]) -> Recipe:
    return build_recipe(
        id=UUID("6f1c2b9e-3d4a-4c5e-9f70-1a2b3c4d5e6f"),
        name="Test recipe",
        prep_minutes=10,
        cook_minutes=20,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
    )


def match(
    ingredient_ids: Sequence[str],
    have: Sequence[str],
    excluded_staples: Sequence[str] = (),
) -> ScoredMatch | AllStaplesMatch | None:
    pantry = resolve_pantry(
        ingredient_ids=have, excluded_staples=excluded_staples, catalog=CATALOG
    )
    return match_recipe(recipe(ingredient_ids), pantry)


def ids(ingredients: Sequence[Ingredient]) -> list[str]:
    return [item.id for item in ingredients]


def scored(result: ScoredMatch | AllStaplesMatch | None) -> ScoredMatch:
    assert isinstance(result, ScoredMatch)
    return result


def test_assumed_staples_make_a_full_match() -> None:
    result = scored(match(ALOO_MATAR, ["potato", "peas"]))

    assert result.match_tenths == 1000
    assert result.score_int == 397940
    assert ids(result.matched) == ["potato", "peas"]
    assert ids(result.missing) == []
    assert ids(result.assumed) == ["tomato", "onion", "turmeric", "salt", "ghee"]


def test_excluded_staple_is_missing_at_a_quarter() -> None:
    result = scored(match(ALOO_MATAR, ["potato", "peas"], ["turmeric"]))

    assert result.match_tenths == 857
    assert ids(result.missing) == ["turmeric"]
    assert ids(result.assumed) == ["tomato", "onion", "salt", "ghee"]


def test_missing_supporting_ingredient() -> None:
    result = scored(match(KHEER, ["rice"]))

    assert result.match_tenths == 667
    assert ids(result.matched) == ["rice"]
    assert ids(result.missing) == ["milk"]
    assert ids(result.assumed) == ["sugar"]


def test_lists_keep_recipe_order() -> None:
    result = scored(match(ALOO_MATAR, ["peas", "potato"]))

    assert ids(result.matched) == ["potato", "peas"]


def test_only_staples_lands_in_the_all_staples_tier() -> None:
    result = match(TOMATO_SOUP, ["potato"])

    assert isinstance(result, AllStaplesMatch)
    assert ids(result.assumed) == TOMATO_SOUP


@pytest.mark.parametrize(
    ("ingredient_ids", "have", "excluded_staples"),
    [
        pytest.param(ALOO_MATAR, ["paneer"], [], id="nothing-matched"),
        pytest.param(TOMATO_SOUP, ["potato"], ["salt"], id="excluded-staple-only"),
    ],
)
def test_not_shown(
    ingredient_ids: list[str], have: list[str], excluded_staples: list[str]
) -> None:
    assert match(ingredient_ids, have, excluded_staples) is None
