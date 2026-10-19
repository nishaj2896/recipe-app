"""Splitting a ranking into swipe decks (ADR-0003 rule 7)."""

from dataclasses import dataclass

from recipe_app.domain.cursor import Position
from recipe_app.domain.matching import AllStaplesMatch, ScoredMatch
from recipe_app.domain.ranking import Ranking, all_staples_sort_key, scored_sort_key

MAX_DECK_SIZE = 20
MAX_ALL_STAPLES_WITH_SCORED = 2


@dataclass(frozen=True, slots=True)
class Deck:
    """One swipe deck: the scored cards, then the all-staples cards."""

    scored: tuple[ScoredMatch, ...]
    all_staples: tuple[AllStaplesMatch, ...]


def build_deck(ranking: Ranking, size: int) -> Deck:
    """Take the next deck from the front of each tier.

    While scored recipes remain, at most 2 all-staples cards follow them, but
    never at the cost of the deck's only scored card. Once the scored tier is
    empty, all-staples cards fill the whole deck.
    """
    if not 1 <= size <= MAX_DECK_SIZE:
        raise ValueError(f"need 1 <= size <= {MAX_DECK_SIZE}, got {size}")

    scored_cap = max(size - MAX_ALL_STAPLES_WITH_SCORED, 1)
    scored = ranking.scored[:scored_cap]
    if scored:
        all_staples_cap = min(MAX_ALL_STAPLES_WITH_SCORED, size - len(scored))
    else:
        all_staples_cap = size
    return Deck(scored=scored, all_staples=ranking.all_staples[:all_staples_cap])


def resume(ranking: Ranking, after: Position) -> Ranking:
    """Everything strictly after the last card shown in each tier (keyset).

    Hidden recipes vanish from the ranking before this runs, which never moves
    the position, so nothing repeats or goes missing (ADR-0003 rule 9).
    """
    scored = ranking.scored
    if after.scored is not None:
        last = after.scored
        scored = tuple(m for m in scored if scored_sort_key(m) > last)
    all_staples = ranking.all_staples
    if after.all_staples is not None:
        last_staple = after.all_staples
        all_staples = tuple(
            m for m in all_staples if all_staples_sort_key(m) > last_staple
        )
    return Ranking(scored=scored, all_staples=all_staples)


def position_after(deck: Deck, before: Position) -> Position:
    """Where the next deck starts: the last card of each tier, or unchanged."""
    return Position(
        scored=scored_sort_key(deck.scored[-1]) if deck.scored else before.scored,
        all_staples=all_staples_sort_key(deck.all_staples[-1])
        if deck.all_staples
        else before.all_staples,
    )
