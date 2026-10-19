"""Deck assembly (ADR-0003 rule 7)."""

from uuid import UUID

import pytest

from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.deck import MAX_DECK_SIZE, Deck, build_deck
from recipe_app.domain.matching import AllStaplesMatch, ScoredMatch
from recipe_app.domain.ranking import Ranking
from recipe_app.domain.recipe import Recipe, build_recipe
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(catalog(category(), ingredient()))


def recipe(number: int) -> Recipe:
    return build_recipe(
        id=UUID(int=number),
        name=f"Recipe {number}",
        prep_minutes=0,
        cook_minutes=30,
        ingredient_ids=["potato"],
        catalog=CATALOG,
    )


def ranking(scored: int, all_staples: int) -> Ranking:
    """Scored recipes are numbered from 1, all-staples ones from 1001.

    build_deck never reads scores or lists, so placeholder values are enough.
    """
    return Ranking(
        scored=tuple(
            ScoredMatch(recipe(n), (), (), (), score_int=0, match_tenths=0)
            for n in range(1, scored + 1)
        ),
        all_staples=tuple(
            AllStaplesMatch(recipe(n), ()) for n in range(1001, 1001 + all_staples)
        ),
    )


def counts(deck: Deck) -> tuple[int, int]:
    return len(deck.scored), len(deck.all_staples)


def skip(source: Ranking, deck: Deck) -> Ranking:
    """What's left after a deck; 7e replaces this with resuming from a cursor."""
    return Ranking(
        scored=source.scored[len(deck.scored) :],
        all_staples=source.all_staples[len(deck.all_staples) :],
    )


def walk(source: Ranking, size: int = MAX_DECK_SIZE) -> list[tuple[int, int]]:
    decks = []
    while source.scored or source.all_staples:
        deck = build_deck(source, size)
        decks.append(counts(deck))
        source = skip(source, deck)
    return decks


@pytest.mark.parametrize(
    ("scored", "all_staples", "expected"),
    [
        pytest.param(30, 10, [(18, 2), (12, 2), (0, 6)], id="adr-example"),
        pytest.param(18, 5, [(18, 2), (0, 3)], id="scored-ends-on-a-full-deck"),
        pytest.param(5, 0, [(5, 0)], id="scored-only"),
        pytest.param(0, 25, [(0, 20), (0, 5)], id="all-staples-only"),
        pytest.param(40, 0, [(18, 0), (18, 0), (4, 0)], id="no-all-staples"),
    ],
)
def test_deck_mix(
    scored: int, all_staples: int, expected: list[tuple[int, int]]
) -> None:
    assert walk(ranking(scored, all_staples)) == expected


def test_empty_ranking_gives_an_empty_deck() -> None:
    assert counts(build_deck(ranking(0, 0), MAX_DECK_SIZE)) == (0, 0)


def test_deck_takes_the_front_of_each_tier_in_order() -> None:
    source = ranking(30, 10)

    deck = build_deck(source, MAX_DECK_SIZE)

    assert deck.scored == source.scored[:18]
    assert deck.all_staples == source.all_staples[:2]


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        pytest.param(20, (18, 2), id="20"),
        pytest.param(10, (8, 2), id="10"),
        pytest.param(3, (1, 2), id="3"),
        pytest.param(2, (1, 1), id="2-keeps-one-scored"),
        pytest.param(1, (1, 0), id="1-keeps-one-scored"),
    ],
)
def test_small_decks_hold_up_to_two_all_staples(
    size: int, expected: tuple[int, int]
) -> None:
    """7b.4: the all-staples cap stays 2 at every size, but a deck never loses
    its scored cards to it."""
    assert counts(build_deck(ranking(30, 10), size)) == expected


def test_small_all_staples_deck_fills_to_size() -> None:
    assert counts(build_deck(ranking(0, 10), 3)) == (0, 3)


@pytest.mark.parametrize("size", [0, -1, 21])
def test_size_out_of_range_raises(size: int) -> None:
    with pytest.raises(ValueError, match="size"):
        build_deck(ranking(1, 1), size)
