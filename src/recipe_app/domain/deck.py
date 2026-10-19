"""Splitting a ranking into swipe decks (ADR-0003 rule 7)."""

from dataclasses import dataclass

from recipe_app.domain.matching import AllStaplesMatch, ScoredMatch
from recipe_app.domain.ranking import Ranking

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
