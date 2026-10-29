"""The recipe files, data/recipes/*.toml, parsed and checked (ADR-0008 rules 2 to 4)."""

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.content import CONTENT_FIELDS, RecipeContent, build_content
from recipe_app.domain.normalization import normalize
from recipe_app.domain.recipe import (
    Recipe,
    RecipeError,
    build_recipe,
    check_recipe,
)
from recipe_app.domain.steps import StepMatcher, step_matcher

RECIPE_FIELDS = (
    frozenset({"id", "name", "prep_minutes", "cook_minutes", "ingredients"})
    | CONTENT_FIELDS
)


@dataclass(frozen=True, slots=True)
class RecipeBook:
    """Every recipe in file order, and what a cook needs for each, by recipe id."""

    recipes: tuple[Recipe, ...]
    content: Mapping[UUID, RecipeContent]


def parse_recipe_book(
    files: Sequence[tuple[str, bytes]], catalog: IngredientCatalog
) -> RecipeBook:
    """Parse every recipe file, in the order given, into one book.

    Every recipe goes through build_recipe and build_content; on top of that
    ids must be canonical UUIDs, and ids and normalized names unique across
    all the files. Collects every problem before raising, like parse_catalog.
    """
    if not files:
        raise RecipeError(["there are no recipe files"])
    matcher = step_matcher(catalog)
    problems: list[str] = []
    recipes: list[Recipe] = []
    content: dict[UUID, RecipeContent] = {}
    seen_ids: set[UUID] = set()
    seen_names: set[str] = set()
    for file_name, raw in files:
        for recipe, recipe_content in _parse_file(
            file_name, raw, catalog, matcher, seen_ids, seen_names, problems
        ):
            recipes.append(recipe)
            content[recipe.id] = recipe_content
    if problems:
        raise RecipeError(problems)
    return RecipeBook(recipes=tuple(recipes), content=MappingProxyType(content))


def _parse_file(
    file_name: str,
    raw: bytes,
    catalog: IngredientCatalog,
    matcher: StepMatcher,
    seen_ids: set[UUID],
    seen_names: set[str],
    problems: list[str],
) -> list[tuple[Recipe, RecipeContent]]:
    if not raw.strip():
        problems.append(f"{file_name}: the file is empty")
        return []
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        problems.append(f"{file_name}: not valid TOML: {error}")
        return []

    problems.extend(
        f"{file_name}: unknown top-level key {key!r}"
        for key in sorted(data)
        if key != "recipe"
    )
    rows = data.get("recipe")
    if not isinstance(rows, list) or not rows:
        problems.append(f"{file_name}: no [[recipe]] entries")
        return []

    parsed: list[tuple[Recipe, RecipeContent]] = []
    for number, row in enumerate(rows, start=1):
        where = f"{file_name} recipe #{number}"
        if not isinstance(row, dict):
            problems.append(f"{where} is not a table")
            continue
        problems.extend(
            f"{where}: unknown field {field!r}"
            for field in sorted(set(row) - RECIPE_FIELDS)
        )

        recipe_id = _recipe_id(row.get("id"), where, problems)
        if recipe_id is not None:
            if recipe_id in seen_ids:
                problems.append(f"{where}: duplicate recipe id {str(recipe_id)!r}")
            seen_ids.add(recipe_id)
        name = row.get("name")
        if isinstance(name, str) and name.strip():
            if normalize(name) in seen_names:
                problems.append(f"{where}: duplicate recipe name {normalize(name)!r}")
            seen_names.add(normalize(name))
        entries = _entries(row.get("ingredients"), where, problems)
        if entries is None:
            # Checking an empty list would add a misleading "has no ingredients".
            continue
        ingredient_ids = [entry["id"] for entry in entries]
        if recipe_id is None:
            # No id to name it by, but the other mistakes still show this run.
            found, _ = check_recipe(
                name=name,  # type: ignore[arg-type]  # check_recipe checks it
                prep_minutes=row.get("prep_minutes"),  # type: ignore[arg-type]
                cook_minutes=row.get("cook_minutes"),  # type: ignore[arg-type]
                ingredient_ids=ingredient_ids,  # type: ignore[arg-type]
                catalog=catalog,
            )
            problems.extend(f"{where}: {problem}" for problem in found)
            continue

        try:
            recipe = build_recipe(
                id=recipe_id,
                name=name,  # type: ignore[arg-type]  # build_recipe checks it
                prep_minutes=row.get("prep_minutes"),  # type: ignore[arg-type]
                cook_minutes=row.get("cook_minutes"),  # type: ignore[arg-type]
                ingredient_ids=ingredient_ids,  # type: ignore[arg-type]
                catalog=catalog,
            )
        except RecipeError as error:
            problems.extend(f"{where}: {problem}" for problem in error.problems)
            continue
        recipe_content, found = build_content(row, entries, recipe, matcher)
        if recipe_content is None:
            problems.extend(f"{where} ({recipe.name}): {problem}" for problem in found)
            continue
        parsed.append((recipe, recipe_content))
    return parsed


def _entries(
    value: object, where: str, problems: list[str]
) -> list[dict[str, object]] | None:
    """The ingredient tables, each with a string id, or None if the list is unusable."""
    if not isinstance(value, list) or not all(
        isinstance(entry, dict) and isinstance(entry.get("id"), str) for entry in value
    ):
        problems.append(
            f"{where}: ingredients must be a list of tables, each with an id"
        )
        return None
    return value


def _recipe_id(value: object, where: str, problems: list[str]) -> UUID | None:
    """Only the canonical lowercase form, so one id is never spelled two ways."""
    if isinstance(value, str):
        try:
            parsed = UUID(value)
        except ValueError:
            pass
        else:
            if str(parsed) == value:
                return parsed
    problems.append(f"{where}: id must be a lowercase UUID string, got {value!r}")
    return None
