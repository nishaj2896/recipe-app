import pytest

from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.steps import states_amount, step_matcher
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="coconut", name="Coconut"),
        ingredient(id="coconut-milk", name="Coconut milk"),
        ingredient(id="coconut-oil", name="Coconut oil", **{"class": "B"}),
        ingredient(id="milk", name="Milk", **{"class": "B"}),
        ingredient(id="oil", name="Oil", **{"class": "S"}, kind="pantry"),
        ingredient(
            id="green-chillies",
            name="Green chillies",
            **{"class": "S"},
            kind="fresh",
            search_terms=["green chilli"],
        ),
        ingredient(id="cherry", name="Cherry"),
        ingredient(id="tomato", name="Tomato", **{"class": "S"}, kind="fresh"),
        ingredient(id="leek", name="Leek", retired=True),
    )
)
MATCHER = step_matcher(CATALOG)


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        pytest.param("Pour in the coconut milk.", ["coconut-milk"], id="coconut-milk"),
        pytest.param("Heat the coconut oil.", ["coconut-oil"], id="coconut-oil"),
        pytest.param(
            "Slit the green chillies.", ["green-chillies"], id="green-chillies"
        ),
        pytest.param("Add a green chilli.", ["green-chillies"], id="search-term"),
        pytest.param(
            "Grate the coconut, then add the milk.", ["coconut", "milk"], id="apart"
        ),
        pytest.param("Boil the potatoes.", ["potato"], id="plural-s"),
        pytest.param("Chop the tomatoes.", ["tomato"], id="plural-es"),
        pytest.param("Pit the cherries.", ["cherry"], id="plural-ies"),
        pytest.param("Bring to a boil, then oil the tin.", ["oil"], id="whole-words"),
        pytest.param("POTATO, potato and Potato!", ["potato"] * 3, id="normalized"),
        pytest.param("Trim the leek.", [], id="retired"),
    ],
)
def test_mentions(step: str, expected: list[str]) -> None:
    assert MATCHER.mentions(step) == expected


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        ("Add 2 cups of water.", "2 cups"),
        ("Add 2 cup water.", "2 cup"),
        ("Add 3 cloves of garlic.", "3 cloves"),
        ("Stir in ½ tsp turmeric.", "1\u20442 tsp"),
        ("Stir in 1/2 cup cream.", "1/2 cup"),
        ("Stir in 1½ cups stock.", "11\u20442 cups"),
        ("Stir in 1.5 l stock.", "1.5 l"),
        ("Fry 200g onions.", "200g"),
        ("Crush two cloves.", "two cloves"),
        ("Add half of a cup.", "a cup"),
        ("Add a pinch of salt.", "a pinch"),
        ("Tear in four leaves.", "four leaves"),
    ],
)
def test_states_amount(step: str, expected: str) -> None:
    assert states_amount(step) == expected


@pytest.mark.parametrize(
    "step",
    [
        "Simmer for 10 minutes.",
        "Bake at 180 °C.",
        "Cut into 2 cm cubes.",
        "Heat a large pan over a medium heat.",
        "Keep back a mugful of the cooking water.",
        "Add the water in two goes.",
        "Strain into cups and serve.",
        "Often stir.",
    ],
)
def test_allows(step: str) -> None:
    assert states_amount(step) is None
