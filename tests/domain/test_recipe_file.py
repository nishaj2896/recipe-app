import json

import pytest

from recipe_app.domain.book import parse_recipe_book
from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.recipe import RecipeError
from recipe_app.domain.units import Unit
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="peas", name="Peas", **{"class": "B"}),
        ingredient(id="leek", name="Leek", **{"class": "B"}, retired=True),
        ingredient(id="salt", name="Salt", **{"class": "S"}, kind="pantry"),
    )
)
RECIPE_ID = "019a0c3e-8f00-7a1b-9c2d-3e4f5a6b7c8d"
OTHER_ID = "019a0c3e-8f01-7a1b-9c2d-3e4f5a6b7c8d"
INGREDIENTS = [
    {"id": "potato", "amount": 2, "unit": "medium"},
    {"id": "peas", "amount": 0.5, "unit": "cup"},
]
STEPS = ["Boil the potatoes until tender.", "Add the peas and simmer for 5 minutes."]


def recipe_table(**fields: object) -> str:
    """A valid [[recipe]] table. Override fields; None drops one."""
    row: dict[str, object] = {
        "id": RECIPE_ID,
        "name": "Aloo matar",
        "serves": 4,
        "prep_minutes": 10,
        "cook_minutes": 20,
        "ingredients": INGREDIENTS,
        "steps": STEPS,
    } | fields
    lines = [
        f"{key} = {_toml(value)}" for key, value in row.items() if value is not None
    ]
    return "[[recipe]]\n" + "\n".join(lines) + "\n"


def _toml(value: object) -> str:
    """Enough TOML for these tests: inline tables, lists, strings and numbers."""
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    return json.dumps(value)


def parse(*tables: str, name: str = "a.toml") -> list[str]:
    """The problems parse_recipe_book reports, or [] if the file is valid."""
    try:
        parse_recipe_book([(name, "\n".join(tables).encode())], CATALOG)
    except RecipeError as error:
        return error.problems
    return []


def test_valid_file_keeps_file_order() -> None:
    raw = (recipe_table() + recipe_table(id=OTHER_ID, name="Peas pulao")).encode()

    book = parse_recipe_book([("a.toml", raw)], CATALOG)

    assert [str(recipe.id) for recipe in book.recipes] == [RECIPE_ID, OTHER_ID]
    assert [item.id for item in book.recipes[0].ingredients] == ["potato", "peas"]


def test_content_follows_ingredient_order() -> None:
    raw = recipe_table(
        ingredients=[*INGREDIENTS, {"id": "salt", "to_taste": True}]
    ).encode()

    book = parse_recipe_book([("a.toml", raw)], CATALOG)
    content = book.content[book.recipes[0].id]

    assert content.serves == 4
    assert [(a.value, a.unit) if a else None for a in content.amounts] == [
        (2, Unit.MEDIUM),
        (0.5, Unit.CUP),
        None,
    ]
    assert content.steps == tuple(STEPS)
    assert content.image is None


def test_files_keep_the_order_given() -> None:
    book = parse_recipe_book(
        [
            ("a.toml", recipe_table().encode()),
            ("b.toml", recipe_table(id=OTHER_ID, name="Peas pulao").encode()),
        ],
        CATALOG,
    )

    assert [str(recipe.id) for recipe in book.recipes] == [RECIPE_ID, OTHER_ID]


def test_no_files() -> None:
    with pytest.raises(RecipeError, match="no recipe files"):
        parse_recipe_book([], CATALOG)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(b"", "a.toml: the file is empty", id="empty"),
        pytest.param(b"  \n", "a.toml: the file is empty", id="blank"),
        pytest.param(b"[[recipe]\n", "a.toml: not valid TOML", id="bad-toml"),
        pytest.param(b"title = 'x'\n", "unknown top-level key 'title'", id="extra-key"),
    ],
)
def test_bad_file(raw: bytes, expected: str) -> None:
    with pytest.raises(RecipeError) as caught:
        parse_recipe_book([("a.toml", raw)], CATALOG)

    assert any(expected in problem for problem in caught.value.problems)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param({"servings": 2}, "unknown field 'servings'", id="unknown-field"),
        pytest.param({"id": None}, "id must be a lowercase UUID", id="no-id"),
        pytest.param({"id": "not-a-uuid"}, "id must be a lowercase UUID", id="bad-id"),
        pytest.param(
            {"id": RECIPE_ID.upper()}, "id must be a lowercase UUID", id="upper-id"
        ),
        pytest.param(
            {"id": RECIPE_ID.replace("-", "")},
            "id must be a lowercase UUID",
            id="unhyphenated-id",
        ),
        pytest.param({"ingredients": "potato"}, "list of tables", id="ingredients-str"),
        pytest.param({"ingredients": ["potato"]}, "list of tables", id="bare-ids"),
        pytest.param(
            {"ingredients": [{"id": "okra", "amount": 1, "unit": "cup"}]},
            "unknown ingredient",
            id="unknown",
        ),
        pytest.param(
            {"ingredients": [{"id": "leek", "amount": 1, "unit": "cup"}]},
            "retired ingredient",
            id="retired",
        ),
        pytest.param({"prep_minutes": "10"}, "prep_minutes must be", id="minutes-str"),
        pytest.param({"name": None}, "name must be", id="no-name"),
        pytest.param({"serves": None}, "serves must be", id="no-serves"),
        pytest.param({"serves": 0}, "serves must be", id="serves-zero"),
        pytest.param({"serves": 13}, "serves must be", id="serves-13"),
        pytest.param({"serves": True}, "serves must be", id="serves-bool"),
        pytest.param({"steps": None}, "steps must be a list", id="no-steps"),
        pytest.param({"steps": STEPS[:1]}, "needs 2 to 20 steps", id="one-step"),
        pytest.param(
            {"steps": [*STEPS, "  Serve. "]}, "extra whitespace", id="step-whitespace"
        ),
        pytest.param({"steps": [*STEPS, "x" * 401]}, "over 400", id="long-step"),
    ],
)
def test_bad_recipe(fields: dict[str, object], expected: str) -> None:
    problems = parse(recipe_table(**fields))

    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        pytest.param({"id": "potato"}, "needs an amount and a unit", id="nothing"),
        pytest.param({"id": "potato", "amount": 2}, "unknown unit None", id="no-unit"),
        pytest.param(
            {"id": "potato", "amount": 2, "unit": "inch"}, "unknown unit", id="inch"
        ),
        pytest.param(
            {"id": "potato", "amount": "2", "unit": "medium"},
            "needs an amount",
            id="amount-str",
        ),
        pytest.param(
            {"id": "potato", "amount": True, "unit": "medium"},
            "needs an amount",
            id="amount-bool",
        ),
        pytest.param(
            {"id": "potato", "amount": 0.3, "unit": "medium"},
            "not on the medium grid",
            id="off-grid",
        ),
        pytest.param(
            {"id": "potato", "to_taste": True, "amount": 2, "unit": "medium"},
            "both an amount and to_taste",
            id="both",
        ),
        pytest.param(
            {"id": "potato", "to_taste": "yes"}, "true or false", id="to-taste-str"
        ),
        pytest.param(
            {"id": "potato", "amount": 2, "unit": "medium", "note": "diced"},
            "unknown field 'note'",
            id="extra-field",
        ),
    ],
)
def test_bad_ingredient_entry(entry: dict[str, object], expected: str) -> None:
    problems = parse(recipe_table(ingredients=[entry, INGREDIENTS[1]]))

    assert any(expected in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(
            ["Boil the potatoes.", "Serve."], "no step names 'peas'", id="forgotten"
        ),
        pytest.param(
            [*STEPS, "Season with salt."],
            "step 3 names 'salt', which the recipe doesn't list",
            id="unlisted",
        ),
        pytest.param(
            [*STEPS, "Add 2 cups of peas."], "step 3 states an amount", id="amount"
        ),
    ],
)
def test_step_checks(steps: list[str], expected: str) -> None:
    problems = parse(recipe_table(steps=steps))

    assert any(expected in problem for problem in problems), problems


def test_a_shared_phrase_counts_as_the_listed_owner() -> None:
    """ "Mint" belongs to fresh and dried mint; the recipe lists only one."""
    shared = parse_catalog(
        catalog(
            category(),
            ingredient(),
            ingredient(id="mint", name="Mint", search_terms=["fresh mint"]),
            ingredient(id="dried-mint", name="Dried mint", search_terms=["mint"]),
        )
    )
    raw = recipe_table(
        ingredients=[
            {"id": "potato", "amount": 2, "unit": "medium"},
            {"id": "dried-mint", "amount": 1, "unit": "tsp"},
        ],
        steps=["Boil the potatoes.", "Toss them with the mint."],
    ).encode()

    book = parse_recipe_book([("a.toml", raw)], shared)

    assert len(book.recipes) == 1


def test_staples_need_not_appear_in_steps() -> None:
    assert (
        parse(
            recipe_table(ingredients=[*INGREDIENTS, {"id": "salt", "to_taste": True}])
        )
        == []
    )


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        pytest.param("photo.webp", "image must be a table", id="not-a-table"),
        pytest.param(
            {"file": "other.webp", "sha256": "a" * 64, "alt": "Aloo matar"},
            f"image file must be '{RECIPE_ID}.webp'",
            id="wrong-file",
        ),
        pytest.param(
            {"file": f"{RECIPE_ID}.webp", "sha256": "A" * 64, "alt": "Aloo matar"},
            "sha256 must be 64 lowercase hex",
            id="upper-hash",
        ),
        pytest.param(
            {"file": f"{RECIPE_ID}.webp", "sha256": "a" * 64, "alt": " "},
            "alt must be",
            id="blank-alt",
        ),
    ],
)
def test_bad_image(image: object, expected: str) -> None:
    problems = parse(recipe_table(image=image))

    assert any(expected in problem for problem in problems), problems


def test_image_is_kept() -> None:
    image = {"file": f"{RECIPE_ID}.webp", "sha256": "a" * 64, "alt": "Aloo matar"}
    book = parse_recipe_book([("a.toml", recipe_table(image=image).encode())], CATALOG)

    found = book.content[book.recipes[0].id].image

    assert found is not None
    assert (found.file, found.sha256, found.alt) == (
        image["file"],
        "a" * 64,
        "Aloo matar",
    )


def test_duplicate_id() -> None:
    problems = parse(recipe_table(), recipe_table(name="Peas pulao"))

    assert problems == [f"a.toml recipe #2: duplicate recipe id {RECIPE_ID!r}"]


def test_duplicate_id_across_files() -> None:
    with pytest.raises(RecipeError) as caught:
        parse_recipe_book(
            [
                ("a.toml", recipe_table().encode()),
                ("b.toml", recipe_table(name="Peas pulao").encode()),
            ],
            CATALOG,
        )

    assert caught.value.problems == [
        f"b.toml recipe #1: duplicate recipe id {RECIPE_ID!r}"
    ]


def test_duplicate_name_after_normalization() -> None:
    problems = parse(recipe_table(), recipe_table(id=OTHER_ID, name="ALOO MATAR"))

    assert problems == ["a.toml recipe #2: duplicate recipe name 'aloo matar'"]


def test_reports_every_problem_at_once() -> None:
    problems = parse(
        recipe_table(servings=2),
        recipe_table(
            id=OTHER_ID,
            name="Peas pulao",
            ingredients=[{"id": "okra", "amount": 1, "unit": "cup"}],
        ),
    )

    assert len(problems) == 2


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param({"id": "not-a-uuid"}, id="bad-id"),
        pytest.param({"ingredients": "potato"}, id="bad-ingredients"),
    ],
)
def test_unparsable_row_reports_one_problem(fields: dict[str, object]) -> None:
    """No placeholder id in the message, and no extra "has no ingredients"."""
    problems = parse(recipe_table(**fields))

    assert len(problems) == 1
    assert "00000000" not in problems[0]


def test_recipe_problems_name_the_file_and_entry() -> None:
    problems = parse(
        recipe_table(), recipe_table(id=OTHER_ID, name="Peas pulao", serves=0)
    )

    assert problems[0].startswith("a.toml recipe #2 (Peas pulao): ")


def test_bad_id_still_reports_the_rows_other_problems() -> None:
    problems = parse(
        recipe_table(
            id="not-a-uuid", ingredients=[{"id": "okra", "amount": 1, "unit": "cup"}]
        )
    )

    assert len(problems) == 2
    assert "unknown ingredient 'okra'" in problems[1]
    assert not any("00000000" in problem for problem in problems)
