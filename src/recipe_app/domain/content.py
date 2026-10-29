"""What a cook needs beyond the matcher: servings, amounts, steps, photo (ADR-0008)."""

import re
from dataclasses import dataclass

from recipe_app.domain.catalog import IngredientClass
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.steps import StepMatcher, states_amount
from recipe_app.domain.units import Unit, on_grid

CONTENT_FIELDS = frozenset({"serves", "steps", "image"})
INGREDIENT_ENTRY_FIELDS = frozenset({"id", "amount", "unit", "to_taste"})
IMAGE_FIELDS = frozenset({"file", "sha256", "alt"})

MIN_SERVES, MAX_SERVES = 1, 12
MIN_STEPS, MAX_STEPS = 2, 20
MAX_STEP_LENGTH = 400
MAX_ALT_LENGTH = 200
SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class Amount:
    value: float
    unit: Unit


@dataclass(frozen=True, slots=True)
class Image:
    file: str
    sha256: str
    alt: str


@dataclass(frozen=True, slots=True)
class RecipeContent:
    """Build it with build_content; `amounts` follows the recipe's ingredient order.

    An amount of None means the ingredient is to taste.
    """

    serves: int
    amounts: tuple[Amount | None, ...]
    steps: tuple[str, ...]
    image: Image | None


@dataclass(frozen=True, slots=True)
class RecipeWithContent:
    """A recipe and its content, read together so the two always agree.

    `content` is None for a recipe synced before it had content.
    """

    recipe: Recipe
    content: RecipeContent | None


def build_content(
    row: dict[str, object],
    entries: list[dict[str, object]],
    recipe: Recipe,
    matcher: StepMatcher,
) -> tuple[RecipeContent | None, list[str]]:
    """Check one recipe's content against ADR-0008 rules 2 and 4.

    `entries` are the recipe's ingredient tables, already known to name the
    recipe's ingredients in order. Returns every problem, without naming the
    recipe, and the content when there are none.
    """
    problems: list[str] = []
    serves = row.get("serves")
    if type(serves) is not int or not MIN_SERVES <= serves <= MAX_SERVES:
        problems.append(
            f"serves must be a whole number from {MIN_SERVES} to {MAX_SERVES}"
        )

    amounts = [_amount(entry, problems) for entry in entries]
    steps = _steps(row.get("steps"), problems)
    image = _image(row.get("image"), recipe, problems)
    if steps:
        _check_steps(steps, recipe, matcher, problems)

    if problems:
        return None, problems
    return (
        RecipeContent(
            serves=serves,  # type: ignore[arg-type]  # checked above
            amounts=tuple(amounts),
            steps=tuple(steps),
            image=image,
        ),
        [],
    )


def _amount(entry: dict[str, object], problems: list[str]) -> Amount | None:
    ingredient_id = entry.get("id")
    where = f"ingredient {ingredient_id!r}"
    problems.extend(
        f"{where}: unknown field {field!r}"
        for field in sorted(set(entry) - INGREDIENT_ENTRY_FIELDS)
    )
    to_taste = entry.get("to_taste", False)
    has_amount = "amount" in entry or "unit" in entry
    if to_taste is not False and to_taste is not True:
        problems.append(f"{where}: to_taste must be true or false")
        return None
    if to_taste and has_amount:
        problems.append(f"{where}: has both an amount and to_taste")
        return None
    if to_taste:
        return None

    value = entry.get("amount")
    unit_text = entry.get("unit")
    # type(...) is not bool: True is an int too, and means nothing here.
    if type(value) not in {int, float}:
        problems.append(f"{where}: needs an amount and a unit, or to_taste = true")
        return None
    try:
        unit = Unit(unit_text)  # type: ignore[arg-type]  # checked by Unit()
    except ValueError:
        problems.append(f"{where}: unknown unit {unit_text!r}")
        return None
    amount = float(value)  # type: ignore[arg-type]  # checked above
    if not on_grid(amount, unit):
        problems.append(f"{where}: {amount:g} {unit} is not on the {unit} grid")
        return None
    return Amount(value=amount, unit=unit)


def _steps(value: object, problems: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(step, str) for step in value):
        problems.append("steps must be a list of strings")
        return []
    if not MIN_STEPS <= len(value) <= MAX_STEPS:
        problems.append(f"needs {MIN_STEPS} to {MAX_STEPS} steps, has {len(value)}")
    for number, step in enumerate(value, start=1):
        if step != " ".join(step.split()) or not step:
            problems.append(f"step {number} is empty or has extra whitespace")
        elif len(step) > MAX_STEP_LENGTH:
            problems.append(f"step {number} is over {MAX_STEP_LENGTH} characters")
        elif (amount := states_amount(step)) is not None:
            problems.append(f"step {number} states an amount: {amount!r}")
    return list(value)


def _check_steps(
    steps: list[str], recipe: Recipe, matcher: StepMatcher, problems: list[str]
) -> None:
    listed = {item.id for item in recipe.ingredients}
    named: set[str] = set()
    for number, step in enumerate(steps, start=1):
        unlisted: list[str] = []
        for owners in matcher.mentions(step):
            # A phrase two ingredients share counts as the one the recipe lists.
            found = [owner for owner in owners if owner in listed]
            named.update(found)
            if not found:
                unlisted.append(" or ".join(repr(owner) for owner in owners))
        problems.extend(
            f"step {number} names {owners}, which the recipe doesn't list"
            for owners in dict.fromkeys(unlisted)
        )
    problems.extend(
        f"no step names {item.id!r}"
        for item in recipe.ingredients
        if item.ingredient_class is not IngredientClass.STAPLE and item.id not in named
    )


def _image(value: object, recipe: Recipe, problems: list[str]) -> Image | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        problems.append("image must be a table")
        return None
    before = len(problems)
    problems.extend(
        f"image: unknown field {field!r}" for field in sorted(set(value) - IMAGE_FIELDS)
    )
    file, sha256, alt = value.get("file"), value.get("sha256"), value.get("alt")
    if file != f"{recipe.id}.webp":
        problems.append(f"image file must be '{recipe.id}.webp', got {file!r}")
    if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
        problems.append("image sha256 must be 64 lowercase hex characters")
    if not isinstance(alt, str) or not alt.strip() or len(alt) > MAX_ALT_LENGTH:
        problems.append(f"image alt must be 1 to {MAX_ALT_LENGTH} characters")
    if len(problems) > before:
        return None
    return Image(file=file, sha256=sha256, alt=alt)  # type: ignore[arg-type]  # checked
