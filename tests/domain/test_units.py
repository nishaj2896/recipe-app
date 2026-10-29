import pytest

from recipe_app.domain.units import Unit, UnitKind, on_grid


@pytest.mark.parametrize(
    ("amount", "unit"),
    [
        (5, Unit.G),
        (95, Unit.G),
        (100, Unit.G),
        (750, Unit.ML),
        (1.25, Unit.KG),
        (0.05, Unit.L),
        (0.25, Unit.TSP),
        (0.333, Unit.CUP),
        (0.667, Unit.TBSP),
        (1.5, Unit.CUP),
        (2.333, Unit.CUP),
        (0.5, Unit.MEDIUM),
        (1.5, Unit.BUNCH),
        (1, Unit.CLOVE),
        (12, Unit.LEAF),
    ],
)
def test_on_grid(amount: float, unit: Unit) -> None:
    assert on_grid(amount, unit)


@pytest.mark.parametrize(
    ("amount", "unit"),
    [
        (0, Unit.G),
        (-5, Unit.G),
        (7, Unit.G),
        (105, Unit.G),
        (1.23, Unit.KG),
        (0.2, Unit.TSP),
        (0.3, Unit.CUP),
        (0.25, Unit.MEDIUM),
        (0.5, Unit.CAN),
        (1.5, Unit.PIECE),
    ],
)
def test_off_grid(amount: float, unit: Unit) -> None:
    assert not on_grid(amount, unit)


def test_thirds_allow_three_decimal_places_only() -> None:
    """0.333 is a third; 0.34 is not, so a typo doesn't pass as one."""
    assert on_grid(0.333, Unit.TSP)
    assert not on_grid(0.34, Unit.TSP)


def test_every_unit_has_a_kind_and_a_plural() -> None:
    assert {unit.kind for unit in Unit} == set(UnitKind)
    assert all(unit.plural for unit in Unit)
    assert Unit.LEAF.plural == "leaves"
    assert Unit.CUP.plural == "cups"
    assert Unit.TSP.plural == "tsp"
