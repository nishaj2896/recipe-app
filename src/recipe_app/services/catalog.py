"""The catalog as the picker and the staples screen show it (ADR-0002 rule 8)."""

from dataclasses import dataclass
from itertools import groupby

from recipe_app.domain.catalog import (
    Category,
    Ingredient,
    IngredientCatalog,
    IngredientClass,
    StapleKind,
)
from recipe_app.domain.normalization import normalize


@dataclass(frozen=True, slots=True)
class CategoryGroup:
    category: Category
    ingredients: tuple[Ingredient, ...]


@dataclass(frozen=True, slots=True)
class StapleGroup:
    kind: StapleKind
    categories: tuple[CategoryGroup, ...]


def listed_ingredients(catalog: IngredientCatalog) -> tuple[Ingredient, ...]:
    """Every live ingredient, by category position, then name."""
    live = [item for item in catalog.by_id.values() if not item.retired]
    return tuple(sorted(live, key=lambda item: _order(catalog, item)))


def staple_groups(catalog: IngredientCatalog) -> tuple[StapleGroup, ...]:
    """Live class S ingredients by kind, then category position, then name."""
    staples = [
        item
        for item in listed_ingredients(catalog)
        if item.ingredient_class is IngredientClass.STAPLE
    ]
    groups: list[StapleGroup] = []
    for kind in StapleKind:
        of_kind = [item for item in staples if item.kind is kind]
        categories = tuple(
            CategoryGroup(catalog.categories[category_id], tuple(items))
            for category_id, items in groupby(of_kind, key=lambda item: item.category)
        )
        if categories:
            groups.append(StapleGroup(kind, categories))
    return tuple(groups)


def _order(catalog: IngredientCatalog, item: Ingredient) -> tuple[int, str, str]:
    # The id breaks a tie between names that normalize alike, which the
    # loader already rejects, so the order is total either way.
    position = catalog.categories[item.category].position
    return (position, normalize(item.name), item.id)
