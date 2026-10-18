import re
from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest

from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.matching import (
    IgnoredReason,
    Pantry,
    PantryError,
    resolve_pantry,
)
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="peas", name="Peas", **{"class": "B"}),
        ingredient(id="paneer", name="Paneer", diet="vegetarian"),
        ingredient(id="tomato", name="Tomato", **{"class": "S"}, kind="fresh"),
        ingredient(id="salt", name="Salt", **{"class": "S"}, kind="pantry"),
        ingredient(id="leek", name="Leek", **{"class": "B"}, retired=True),
        ingredient(
            id="hing", name="Hing", **{"class": "S"}, kind="pantry", retired=True
        ),
    )
)


def resolve(
    ingredient_ids: Sequence[str] = (), excluded_staples: Sequence[str] = ()
) -> Pantry:
    return resolve_pantry(
        ingredient_ids=ingredient_ids,
        excluded_staples=excluded_staples,
        catalog=CATALOG,
    )


def ignored(pantry: Pantry) -> list[tuple[str, IgnoredReason]]:
    return [(item.ingredient.id, item.reason) for item in pantry.ignored]


def test_have_holds_live_main_and_supporting_ingredients() -> None:
    pantry = resolve(["potato", "peas"])

    assert pantry.have == {"potato", "peas"}
    assert pantry.out_of == frozenset()
    assert pantry.ignored == ()


def test_out_of_holds_live_staples() -> None:
    pantry = resolve(["potato"], ["salt", "tomato"])

    assert pantry.out_of == {"salt", "tomato"}
    assert pantry.ignored == ()


@pytest.mark.parametrize(
    ("ingredient_ids", "excluded_staples", "expected"),
    [
        pytest.param(["leek"], [], [("leek", IgnoredReason.RETIRED)], id="retired"),
        pytest.param(
            ["tomato"], [], [("tomato", IgnoredReason.NOW_STAPLE)], id="now-staple"
        ),
        pytest.param(
            [], ["paneer"], [("paneer", IgnoredReason.NOT_STAPLE)], id="not-staple"
        ),
        pytest.param(
            [], ["hing"], [("hing", IgnoredReason.RETIRED)], id="retired-staple"
        ),
        pytest.param(
            [],
            ["leek"],
            [("leek", IgnoredReason.RETIRED)],
            id="retired-beats-not-staple",
        ),
    ],
)
def test_ignored_reasons(
    ingredient_ids: list[str],
    excluded_staples: list[str],
    expected: list[tuple[str, IgnoredReason]],
) -> None:
    pantry = resolve(ingredient_ids, excluded_staples)

    assert ignored(pantry) == expected
    assert pantry.have == frozenset()
    assert pantry.out_of == frozenset()


def test_main_ingredient_in_both_lists_is_matched_and_ignored() -> None:
    pantry = resolve(["paneer"], ["paneer"])

    assert pantry.have == {"paneer"}
    assert ignored(pantry) == [("paneer", IgnoredReason.NOT_STAPLE)]


def test_staple_in_both_lists_is_excluded() -> None:
    pantry = resolve(["tomato"], ["tomato"])

    assert pantry.out_of == {"tomato"}
    assert ignored(pantry) == [("tomato", IgnoredReason.NOW_STAPLE)]


def test_retired_id_in_both_lists_is_listed_once() -> None:
    pantry = resolve(["leek"], ["leek"])

    assert ignored(pantry) == [("leek", IgnoredReason.RETIRED)]


def test_ignored_keeps_request_order() -> None:
    pantry = resolve(["tomato", "potato", "leek"], ["paneer"])

    assert ignored(pantry) == [
        ("tomato", IgnoredReason.NOW_STAPLE),
        ("leek", IgnoredReason.RETIRED),
        ("paneer", IgnoredReason.NOT_STAPLE),
    ]


@pytest.mark.parametrize(
    ("ingredient_ids", "excluded_staples", "message"),
    [
        pytest.param(
            ["potatoe"],
            [],
            "ingredient_ids: unknown ingredient 'potatoe'",
            id="unknown",
        ),
        pytest.param(
            ["potato"],
            ["salty"],
            "excluded_staples: unknown ingredient 'salty'",
            id="unknown-staple",
        ),
        pytest.param(
            ["potato", "potato"],
            [],
            "ingredient_ids: duplicate ingredient 'potato'",
            id="duplicate",
        ),
        pytest.param(
            ["potato"],
            ["salt", "salt"],
            "excluded_staples: duplicate ingredient 'salt'",
            id="duplicate-staple",
        ),
    ],
)
def test_rejects(
    ingredient_ids: list[str], excluded_staples: list[str], message: str
) -> None:
    with pytest.raises(PantryError, match=re.escape(message)):
        resolve(ingredient_ids, excluded_staples)


def test_rejects_with_every_problem() -> None:
    with pytest.raises(PantryError) as error:
        resolve(["potatoe", "peas", "peas"], ["salty"])

    assert error.value.problems == [
        "ingredient_ids: unknown ingredient 'potatoe'",
        "ingredient_ids: duplicate ingredient 'peas'",
        "excluded_staples: unknown ingredient 'salty'",
    ]


def test_pantry_is_read_only() -> None:
    pantry = resolve(["potato"])

    with pytest.raises(FrozenInstanceError):
        pantry.have = frozenset()  # type: ignore[misc]
