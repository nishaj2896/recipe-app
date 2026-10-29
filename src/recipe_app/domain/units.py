"""Units for recipe amounts and the grid each is shown on (ADR-0008 rule 2).

The web app scales amounts with the same grids; a unit added here needs its
forms and grid there too.
"""

from enum import StrEnum
from typing import assert_never

# Thirds are written as 0.333 and 0.667, so every grid check allows this much.
TOLERANCE = 0.005


class UnitKind(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    SPOON = "spoon"
    PRODUCE = "produce"
    COUNT = "count"


class Unit(StrEnum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    TSP = "tsp"
    TBSP = "tbsp"
    CUP = "cup"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    SMALL_HEAD = "small-head"
    BUNCH = "bunch"
    PIECE = "piece"
    CLOVE = "clove"
    SPRIG = "sprig"
    SLICE = "slice"
    LEAF = "leaf"
    PINCH = "pinch"
    CAN = "can"

    @property
    def kind(self) -> UnitKind:
        match self:
            case Unit.G | Unit.KG:
                return UnitKind.MASS
            case Unit.ML | Unit.L:
                return UnitKind.VOLUME
            case Unit.TSP | Unit.TBSP | Unit.CUP:
                return UnitKind.SPOON
            case Unit.SMALL | Unit.MEDIUM | Unit.LARGE | Unit.SMALL_HEAD | Unit.BUNCH:
                return UnitKind.PRODUCE
            case (
                Unit.PIECE
                | Unit.CLOVE
                | Unit.SPRIG
                | Unit.SLICE
                | Unit.LEAF
                | Unit.PINCH
                | Unit.CAN
            ):
                return UnitKind.COUNT
            case _:
                assert_never(self)

    @property
    def plural(self) -> str:
        """The form shown for amounts above 1, and caught in steps (rule 4)."""
        match self:
            case Unit.G | Unit.KG | Unit.ML | Unit.L | Unit.TSP | Unit.TBSP:
                return self.value
            case Unit.SMALL | Unit.MEDIUM | Unit.LARGE:
                return self.value
            case Unit.SMALL_HEAD:
                return "small-heads"
            case Unit.BUNCH:
                return "bunches"
            case Unit.LEAF:
                return "leaves"
            case Unit.PINCH:
                return "pinches"
            case (
                Unit.CUP | Unit.PIECE | Unit.CLOVE | Unit.SPRIG | Unit.SLICE | Unit.CAN
            ):
                return f"{self.value}s"
            case _:
                assert_never(self)


def on_grid(amount: float, unit: Unit) -> bool:
    """Whether a written amount is one the screen shows unchanged (rule 2)."""
    if amount <= 0:
        return False
    if unit in {Unit.KG, Unit.L}:
        return _multiple(amount, 0.05)
    kind = unit.kind
    match kind:
        case UnitKind.MASS | UnitKind.VOLUME:
            return _multiple(amount, 5 if amount < 100 else 10)
        case UnitKind.SPOON:
            return _multiple(amount, 0.25) or _multiple(amount, 1 / 3)
        case UnitKind.PRODUCE:
            return _multiple(amount, 0.5)
        case UnitKind.COUNT:
            return _multiple(amount, 1)
        case _:
            assert_never(kind)


def _multiple(amount: float, step: float) -> bool:
    return abs(amount - round(amount / step) * step) <= TOLERANCE
