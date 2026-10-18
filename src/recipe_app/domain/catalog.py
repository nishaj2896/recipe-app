"""The ingredient catalog, loaded from data/ingredients.v1.toml (ADR-0002 rule 7)."""

import hashlib
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from recipe_app.domain.normalization import normalize

NEVER_STAPLES = frozenset({"milk", "curd"})
MAX_ID_LENGTH = 64
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

CATEGORY_FIELDS = frozenset({"id", "name", "position", "retired"})
INGREDIENT_FIELDS = frozenset(
    {"id", "name", "class", "kind", "diet", "category", "search_terms", "retired"}
)


class IngredientClass(StrEnum):
    MAIN = "A"
    SUPPORTING = "B"
    STAPLE = "S"


class StapleKind(StrEnum):
    FRESH = "fresh"
    PANTRY = "pantry"


class Diet(StrEnum):
    VEGAN = "vegan"
    VEGETARIAN = "vegetarian"
    EGG = "egg"
    NON_VEG = "non_veg"


@dataclass(frozen=True, slots=True)
class Category:
    id: str
    name: str
    position: int
    retired: bool


@dataclass(frozen=True, slots=True)
class Ingredient:
    id: str
    name: str
    ingredient_class: IngredientClass
    kind: StapleKind | None
    diet: Diet
    category: str
    search_terms: tuple[str, ...]
    retired: bool


@dataclass(frozen=True, slots=True)
class IngredientCatalog:
    by_id: Mapping[str, Ingredient]
    categories: Mapping[str, Category]
    content_hash: str


class CatalogError(ValueError):
    """The catalog file breaks one or more rules; `problems` lists every one."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(f"invalid ingredient catalog:\n{lines}")


def parse_catalog(raw: bytes) -> IngredientCatalog:
    """Parse the catalog file and check every rule in ADR-0002 rule 7.

    Collects every problem before raising, so one run of the app or the
    tests shows everything that needs fixing, not just the first mistake.
    """
    if not raw.strip():
        raise CatalogError(["the catalog file is empty"])
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise CatalogError([f"the catalog file is not valid TOML: {error}"]) from error

    problems = [
        f"unknown top-level key {key!r}"
        for key in sorted(data)
        if key not in {"category", "ingredient"}
    ]
    categories = _parse_categories(_tables(data, "category", problems), problems)
    ingredients = _parse_ingredients(_tables(data, "ingredient", problems), problems)

    if not problems:
        # Cross-entry checks need every entry parsed, or one bad entry would
        # also be reported as a missing category or an empty one.
        _check_references(categories, ingredients, problems)
    if problems:
        raise CatalogError(problems)

    return IngredientCatalog(
        by_id=MappingProxyType({item.id: item for item in ingredients}),
        categories=MappingProxyType({item.id: item for item in categories}),
        content_hash=hashlib.sha256(raw).hexdigest(),
    )


def _tables(
    data: dict[str, object], key: str, problems: list[str]
) -> list[dict[str, object]]:
    tables = data.get(key)
    if not isinstance(tables, list) or not tables:
        problems.append(f"the catalog has no [[{key}]] entries")
        return []
    return [table for table in tables if isinstance(table, dict)]


def _parse_categories(
    tables: list[dict[str, object]], problems: list[str]
) -> list[Category]:
    categories: list[Category] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    seen_positions: set[int] = set()
    for number, row in enumerate(tables, start=1):
        where = _where("category", number, row)
        before = len(problems)
        _check_fields(row, CATEGORY_FIELDS, where, problems)
        category_id = _id(row, where, problems)
        name = _text(row, "name", where, problems)
        position = row.get("position")
        if type(position) is not int or position < 1:
            problems.append(f"{where}: position must be a positive integer")
            position = 0
        retired = _retired(row, where, problems)

        if category_id in seen_ids:
            problems.append(f"duplicate category id {category_id!r}")
        if normalize(name) in seen_names:
            problems.append(f"duplicate category name {normalize(name)!r}")
        if position in seen_positions:
            problems.append(f"duplicate category position {position}")
        seen_ids.add(category_id)
        seen_names.add(normalize(name))
        seen_positions.add(position)

        if len(problems) == before:
            categories.append(Category(category_id, name, position, retired))
    return categories


def _parse_ingredients(
    tables: list[dict[str, object]], problems: list[str]
) -> list[Ingredient]:
    ingredients: list[Ingredient] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for number, row in enumerate(tables, start=1):
        where = _where("ingredient", number, row)
        before = len(problems)
        _check_fields(row, INGREDIENT_FIELDS, where, problems)
        ingredient_id = _id(row, where, problems)
        name = _text(row, "name", where, problems)
        ingredient_class = _choice(IngredientClass, row, "class", where, problems)
        diet = _choice(Diet, row, "diet", where, problems)
        category = _text(row, "category", where, problems)
        search_terms = _search_terms(row, where, problems)
        retired = _retired(row, where, problems)

        kind = None
        if "kind" in row:
            kind = _choice(StapleKind, row, "kind", where, problems)
            if ingredient_class not in {IngredientClass.STAPLE, None}:
                problems.append(f"{where}: only class S can have a kind")
        elif ingredient_class is IngredientClass.STAPLE:
            problems.append(f"{where}: class S needs a kind")
        if (
            ingredient_id in NEVER_STAPLES
            and ingredient_class is IngredientClass.STAPLE
        ):
            problems.append(f"{where}: {ingredient_id!r} can never be a staple")

        if ingredient_id in seen_ids:
            problems.append(f"duplicate id {ingredient_id!r}")
        if normalize(name) in seen_names:
            problems.append(f"duplicate name {normalize(name)!r}")
        seen_ids.add(ingredient_id)
        seen_names.add(normalize(name))

        if len(problems) == before and ingredient_class and diet:
            ingredients.append(
                Ingredient(
                    id=ingredient_id,
                    name=name,
                    ingredient_class=ingredient_class,
                    kind=kind,
                    diet=diet,
                    category=category,
                    search_terms=search_terms,
                    retired=retired,
                )
            )
    return ingredients


def _check_references(
    categories: list[Category], ingredients: list[Ingredient], problems: list[str]
) -> None:
    by_id = {category.id: category for category in categories}
    live_categories: set[str] = set()
    for ingredient in ingredients:
        category = by_id.get(ingredient.category)
        if category is None:
            problems.append(
                f"ingredient {ingredient.id!r}: "
                f"unknown category {ingredient.category!r}"
            )
        elif category.retired and not ingredient.retired:
            problems.append(
                f"ingredient {ingredient.id!r}: uses retired category {category.id!r}"
            )
        if not ingredient.retired:
            live_categories.add(ingredient.category)
    for category in categories:
        if not category.retired and category.id not in live_categories:
            problems.append(f"category {category.id!r} has no live ingredients")


def _where(table: str, number: int, row: dict[str, object]) -> str:
    """Name an entry in a problem message by its id, or by its position."""
    row_id = row.get("id")
    if isinstance(row_id, str) and row_id:
        return f"{table} {row_id!r}"
    return f"{table} #{number}"


def _check_fields(
    row: dict[str, object],
    allowed: frozenset[str],
    where: str,
    problems: list[str],
) -> None:
    for field in sorted(set(row) - allowed):
        problems.append(f"{where}: unknown field {field!r}")


def _id(row: dict[str, object], where: str, problems: list[str]) -> str:
    value = _text(row, "id", where, problems)
    if len(value) > MAX_ID_LENGTH:
        problems.append(f"{where}: id is longer than {MAX_ID_LENGTH} characters")
    elif value and not SLUG.fullmatch(value):
        problems.append(f"{where}: id {value!r} is not a slug")
    return value


def _text(row: dict[str, object], field: str, where: str, problems: list[str]) -> str:
    value = row.get(field)
    if isinstance(value, str) and value.strip():
        return value
    problems.append(f"{where}: {field} must be a non-empty string")
    return ""


def _choice[E: StrEnum](
    enum: type[E],
    row: dict[str, object],
    field: str,
    where: str,
    problems: list[str],
) -> E | None:
    value = row.get(field)
    if isinstance(value, str) and value in enum:
        return enum(value)
    problems.append(f"{where}: unknown {field} {value!r}")
    return None


def _search_terms(
    row: dict[str, object], where: str, problems: list[str]
) -> tuple[str, ...]:
    """Return the terms normalized (ADR-0001 rule 4), ready for search to compare."""
    terms = row.get("search_terms", [])
    if not isinstance(terms, list) or not all(
        isinstance(term, str) and term.strip() for term in terms
    ):
        problems.append(f"{where}: search_terms must be a list of non-empty strings")
        return ()
    return tuple(normalize(term) for term in terms)


def _retired(row: dict[str, object], where: str, problems: list[str]) -> bool:
    value = row.get("retired", False)
    if isinstance(value, bool):
        return value
    problems.append(f"{where}: retired must be true or false")
    return False
