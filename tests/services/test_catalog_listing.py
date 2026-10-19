from recipe_app.domain.catalog import IngredientClass, StapleKind, parse_catalog
from recipe_app.domain.normalization import normalize
from recipe_app.infra.data import load_catalog
from recipe_app.services.catalog import listed_ingredients, staple_groups
from tests.domain.factories import catalog, category, ingredient

SMALL = parse_catalog(
    catalog(
        category(id="vegetables", name="Vegetables", position=20),
        category(id="dairy", name="Dairy", position=10),
        category(id="spices", name="Spices", position=30),
        category(id="old", name="Old", position=40, retired=True),
        ingredient(id="potato", name="Potato"),
        ingredient(id="okra", name="okra"),
        ingredient(id="paneer", name="Paneer", category="dairy", diet="vegetarian"),
        ingredient(
            id="ghee",
            name="Ghee",
            category="dairy",
            diet="vegetarian",
            kind="pantry",
            **{"class": "S"},
        ),
        ingredient(
            id="salt", name="Salt", category="spices", kind="pantry", **{"class": "S"}
        ),
        ingredient(id="tomato", name="Tomato", kind="fresh", **{"class": "S"}),
        ingredient(id="leek", name="Leek", category="old", retired=True),
    )
)


def test_ingredients_by_category_position_then_name_without_retired() -> None:
    assert [item.id for item in listed_ingredients(SMALL)] == [
        "ghee",
        "paneer",
        "okra",
        "potato",
        "tomato",
        "salt",
    ]


def test_staples_by_kind_then_category_then_name() -> None:
    groups = staple_groups(SMALL)

    assert [
        (g.kind, [(c.category.id, [i.id for i in c.ingredients]) for c in g.categories])
        for g in groups
    ] == [
        (StapleKind.FRESH, [("vegetables", ["tomato"])]),
        (StapleKind.PANTRY, [("dairy", ["ghee"]), ("spices", ["salt"])]),
    ]


def test_real_catalog_listing_is_complete_and_sorted() -> None:
    real = load_catalog()
    listed = listed_ingredients(real)

    assert len(listed) == sum(not item.retired for item in real.by_id.values())
    keys = [(real.categories[i.category].position, normalize(i.name)) for i in listed]
    assert keys == sorted(keys)


def test_real_staples_are_every_live_staple_once() -> None:
    real = load_catalog()
    shown = [
        item.id
        for group in staple_groups(real)
        for cat in group.categories
        for item in cat.ingredients
    ]

    assert sorted(shown) == sorted(
        item.id
        for item in real.by_id.values()
        if item.ingredient_class is IngredientClass.STAPLE and not item.retired
    )
