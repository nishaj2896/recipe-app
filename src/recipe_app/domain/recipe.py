"""Recipes, built from catalog ingredients; diet is computed (ADR-0002 rule 6).

The recipe files are parsed in domain/book.py.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from recipe_app.domain.catalog import (
    Diet,
    Ingredient,
    IngredientCatalog,
    IngredientClass,
)
from recipe_app.domain.normalization import normalize
from recipe_app.domain.tags import (
    MAX_ALIAS_LENGTH,
    MAX_ALIASES,
    MAX_COURSES,
    MAX_MOODS,
    MAX_PAIRINGS,
    MAX_WEATHER,
    MIN_COURSES,
    MIN_MOODS,
    Allergen,
    Course,
    Cuisine,
    Mood,
    Weather,
)

MAX_TOTAL_MINUTES = 24 * 60

# A wait shorter than an hour fits around the cooking; a week covers any pickle.
MIN_WAIT_MINUTES, MAX_WAIT_MINUTES = 60, 7 * 24 * 60
MAX_WAIT_NOTE_LENGTH = 40
PLAN_AHEAD_FIELDS = frozenset({"wait_minutes", "note"})
TAG_FIELDS = frozenset(
    {"cuisine", "courses", "moods", "weather", "also_known_as", "pairs_with"}
)


@dataclass(frozen=True, slots=True)
class PlanAhead:
    """A hands-off wait of an hour or more that the times leave out (ADR-0009).

    `note` finishes "Plan ahead: ", so it has no capital first letter and no full
    stop: "soak overnight".
    """

    wait_minutes: int
    note: str


@dataclass(frozen=True, slots=True)
class RecipeTags:
    """What the search, the mood screen and pairings read (ADR-0012 rule 1).

    Every field is optional until the content pull requests tag every recipe;
    the lists keep the order written.
    """

    cuisine: Cuisine | None = None
    courses: tuple[Course, ...] = ()
    moods: tuple[Mood, ...] = ()
    weather: tuple[Weather, ...] = ()
    also_known_as: tuple[str, ...] = ()
    pairs_with: tuple[UUID, ...] = ()


NO_TAGS = RecipeTags()


@dataclass(frozen=True, slots=True)
class Image:
    """A recipe's photo: a file in web/public/dishes/, its hash, and its alt text."""

    file: str
    sha256: str
    alt: str


@dataclass(frozen=True, slots=True)
class Recipe:
    """A recipe made only of real catalog ingredients; build it with build_recipe.

    Prep and cook time count hands-on work only; waiting such as soaking,
    fermenting, marinating, resting, chilling or freezing is left out.
    """

    id: UUID
    name: str
    prep_minutes: int
    cook_minutes: int
    ingredients: tuple[Ingredient, ...]
    plan_ahead: PlanAhead | None = None
    # Copied from the recipe's content so the swipe card can show it (ADR-0010).
    image: Image | None = None
    tags: RecipeTags = NO_TAGS

    @property
    def total_minutes(self) -> int:
        return self.prep_minutes + self.cook_minutes

    @property
    def diet(self) -> Diet:
        """The highest diet tag across every ingredient, assumed staples included."""
        return max(
            (ingredient.diet for ingredient in self.ingredients),
            key=lambda diet: diet.rank,
        )

    @property
    def allergens(self) -> tuple[Allergen, ...]:
        """Every ingredient's allergens, in Allergen order (ADR-0012 rule 2)."""
        found = {a for ingredient in self.ingredients for a in ingredient.allergens}
        return tuple(allergen for allergen in Allergen if allergen in found)

    @property
    def jain(self) -> bool:
        """Vegan or vegetarian, with no ingredient a Jain kitchen leaves out."""
        return Diet.VEGETARIAN.allows(self.diet) and all(
            ingredient.jain for ingredient in self.ingredients
        )

    @property
    def all_staples(self) -> bool:
        """Every ingredient is a staple, so any pantry can cook it (ADR-0003)."""
        return all(
            ingredient.ingredient_class is IngredientClass.STAPLE
            for ingredient in self.ingredients
        )


class RecipeError(ValueError):
    """The recipe breaks one or more rules; `problems` lists every one."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        lines = "\n".join(f"- {problem}" for problem in problems)
        super().__init__(f"invalid recipe:\n{lines}")


def build_recipe(
    *,
    id: UUID,
    name: str,
    prep_minutes: int,
    cook_minutes: int,
    ingredient_ids: Sequence[str],
    catalog: IngredientCatalog,
    plan_ahead: object = None,
    tags: Mapping[str, object] | None = None,
) -> Recipe:
    """Resolve every ingredient id against the catalog and check every rule.

    Collects every problem before raising, like parse_catalog, so a seed file
    with several mistakes shows them all in one run.
    """
    problems, ingredients = check_recipe(
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredient_ids=ingredient_ids,
        catalog=catalog,
    )
    wait = check_plan_ahead(plan_ahead, problems)
    recipe_tags = check_tags(tags or {}, name, id, problems)
    if problems:
        raise RecipeError(
            [f"recipe {name!r} ({id}): {problem}" for problem in problems]
        )

    return Recipe(
        id=id,
        name=name,
        prep_minutes=prep_minutes,
        cook_minutes=cook_minutes,
        ingredients=tuple(ingredients),
        plan_ahead=wait,
        tags=recipe_tags,
    )


def check_plan_ahead(value: object, problems: list[str]) -> PlanAhead | None:
    """The `plan_ahead` table as written in a recipe file, or None when absent.

    Adds every problem to `problems`, without naming the recipe.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        problems.append("plan_ahead must be a table")
        return None
    before = len(problems)
    problems.extend(
        f"plan_ahead: unknown field {field!r}"
        for field in sorted(set(value) - PLAN_AHEAD_FIELDS)
    )
    minutes, note = value.get("wait_minutes"), value.get("note")
    # type(...) is int, not isinstance: True is an int too, and means nothing here.
    if type(minutes) is not int or not (
        MIN_WAIT_MINUTES <= minutes <= MAX_WAIT_MINUTES
    ):
        problems.append(
            "plan_ahead wait_minutes must be a whole number from "
            f"{MIN_WAIT_MINUTES} to {MAX_WAIT_MINUTES}"
        )
    if (
        not isinstance(note, str)
        or not note
        or len(note) > MAX_WAIT_NOTE_LENGTH
        or note != " ".join(note.split())
        or note[0].isupper()
        or note.endswith(".")
    ):
        problems.append(
            f"plan_ahead note must be 1 to {MAX_WAIT_NOTE_LENGTH} characters, "
            "single-spaced, must not start with a capital letter or end with a "
            "full stop"
        )
    if len(problems) > before:
        return None
    return PlanAhead(wait_minutes=minutes, note=note)  # type: ignore[arg-type]  # checked


def check_tags(
    row: Mapping[str, object],
    name: object,
    recipe_id: UUID | None,
    problems: list[str],
) -> RecipeTags:
    """The tag fields as written in a recipe file (ADR-0012 rules 1 and 3).

    Every field is optional for now. Checks that `pairs_with` names other
    recipes that exist need the whole book, so parse_recipe_book does those.
    Adds every problem to `problems`, without naming the recipe.
    """
    before = len(problems)
    cuisine = None
    if "cuisine" in row:
        value = row["cuisine"]
        if isinstance(value, str) and value in Cuisine:
            cuisine = Cuisine(value)
        else:
            problems.append(f"unknown cuisine {value!r}")
    courses = _choices(row, "courses", Course, MIN_COURSES, MAX_COURSES, problems)
    moods = _choices(row, "moods", Mood, MIN_MOODS, MAX_MOODS, problems)
    weather = _choices(row, "weather", Weather, 0, MAX_WEATHER, problems)
    aliases = _aliases(row.get("also_known_as", []), name, problems)
    pairs = _pairs(row.get("pairs_with", []), recipe_id, problems)
    if len(problems) > before:
        return NO_TAGS
    return RecipeTags(
        cuisine=cuisine,
        courses=courses,
        moods=moods,
        weather=weather,
        also_known_as=aliases,
        pairs_with=pairs,
    )


def _choices[E: (Course, Mood, Weather)](
    row: Mapping[str, object],
    field: str,
    enum: type[E],
    least: int,
    most: int,
    problems: list[str],
) -> tuple[E, ...]:
    if field not in row:
        return ()
    values = row[field]
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        problems.append(f"{field} must be a list of strings")
        return ()
    if not least <= len(values) <= most:
        problems.append(f"{field} must have {least} to {most} entries")
    if len(set(values)) != len(values):
        problems.append(f"{field} has duplicates")
    unknown = [value for value in values if value not in enum]
    problems.extend(f"unknown {field} entry {value!r}" for value in unknown)
    return tuple(enum(value) for value in values if value in enum)


def _aliases(value: object, name: object, problems: list[str]) -> tuple[str, ...]:
    """Other names people type: lower case, single-spaced, not the name itself."""
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        problems.append("also_known_as must be a list of strings")
        return ()
    if len(value) > MAX_ALIASES:
        problems.append(f"also_known_as must have at most {MAX_ALIASES} entries")
    if len(set(value)) != len(value):
        problems.append("also_known_as has duplicates")
    own = normalize(name) if isinstance(name, str) else None
    for alias in value:
        if (
            not alias
            or len(alias) > MAX_ALIAS_LENGTH
            or alias != " ".join(alias.split())
            or alias != alias.lower()
        ):
            problems.append(
                f"also_known_as {alias!r} must be 1 to {MAX_ALIAS_LENGTH} "
                "characters, lower case and single-spaced"
            )
        elif normalize(alias) == own:
            problems.append(f"also_known_as {alias!r} is the recipe's own name")
    return tuple(value)


def _pairs(
    value: object, recipe_id: UUID | None, problems: list[str]
) -> tuple[UUID, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        problems.append("pairs_with must be a list of recipe ids")
        return ()
    if len(value) > MAX_PAIRINGS:
        problems.append(f"pairs_with must have at most {MAX_PAIRINGS} entries")
    pairs: list[UUID] = []
    for text in value:
        try:
            parsed = UUID(text)
        except ValueError:
            parsed = None
        if parsed is None or str(parsed) != text:
            problems.append(f"pairs_with {text!r} is not a lowercase UUID string")
            continue
        if parsed == recipe_id:
            problems.append("pairs_with names the recipe itself")
        elif parsed in pairs:
            problems.append(f"pairs_with has {text!r} twice")
        pairs.append(parsed)
    return tuple(pairs)


def check_recipe(
    *,
    name: str,
    prep_minutes: int,
    cook_minutes: int,
    ingredient_ids: Sequence[str],
    catalog: IngredientCatalog,
) -> tuple[list[str], list[Ingredient]]:
    """Every per-recipe problem, without naming the recipe, and its ingredients."""
    problems: list[str] = []

    if not isinstance(name, str) or not name.strip():
        problems.append("name must be a non-empty string")
    elif name != " ".join(name.split()):
        problems.append(f"name {name!r} has extra whitespace")

    minutes_ok = True
    for field, value in (
        ("prep_minutes", prep_minutes),
        ("cook_minutes", cook_minutes),
    ):
        # type(...) is int, not isinstance: True is an int too, and means nothing here.
        if type(value) is not int or value < 0:
            problems.append(f"{field} must be a whole number, 0 or more")
            minutes_ok = False
    if minutes_ok:
        total = prep_minutes + cook_minutes
        if total < 1:
            problems.append("total time must be at least 1 minute")
        elif total > MAX_TOTAL_MINUTES:
            problems.append(f"total time must be at most {MAX_TOTAL_MINUTES} minutes")

    if not ingredient_ids:
        problems.append("has no ingredients")
    ingredients: list[Ingredient] = []
    seen: set[str] = set()
    for ingredient_id in ingredient_ids:
        if ingredient_id in seen:
            problems.append(f"duplicate ingredient {ingredient_id!r}")
            continue
        seen.add(ingredient_id)
        found = catalog.by_id.get(ingredient_id)
        if found is None:
            problems.append(f"unknown ingredient {ingredient_id!r}")
        elif found.retired:
            problems.append(f"retired ingredient {ingredient_id!r}")
        else:
            ingredients.append(found)
    return problems, ingredients
