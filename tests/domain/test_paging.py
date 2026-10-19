"""Resuming a deck from a cursor, end to end (ADR-0003 rules 6, 7 and 9)."""

from collections.abc import Sequence
from itertools import cycle
from uuid import UUID

from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.cursor import (
    Position,
    Scope,
    SigningKeys,
    decode_cursor,
    encode_cursor,
    request_fingerprint,
)
from recipe_app.domain.deck import (
    MAX_DECK_SIZE,
    Deck,
    build_deck,
    position_after,
    resume,
)
from recipe_app.domain.matching import resolve_pantry
from recipe_app.domain.ranking import Ranking, SearchFilters, rank
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.domain.scoring import SCORING_VERSION
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(
    catalog(
        category(),
        ingredient(),
        ingredient(id="rice", name="Rice"),
        ingredient(id="peas", name="Peas", **{"class": "B"}),
        ingredient(id="tomato", name="Tomato", **{"class": "S"}, kind="fresh"),
        ingredient(id="salt", name="Salt", **{"class": "S"}, kind="pantry"),
    )
)
PANTRY = resolve_pantry(
    ingredient_ids=["potato", "peas"], excluded_staples=[], catalog=CATALOG
)
KEYS = SigningKeys(active_kid="a", keys={"a": b"a" * 32})
SCOPE = Scope(
    catalog=CATALOG.content_hash,
    scoring=SCORING_VERSION,
    req=request_fingerprint(
        diet=None,
        max_total_minutes=None,
        ingredient_ids=["potato", "peas"],
        excluded_staples=[],
    ),
)
NOW = 1_800_000_000
MAX_PAGES = 100  # a resume bug repeats a deck forever; stop and fail instead

# Few distinct scores and times, so most recipes tie and the id decides.
SCORED_SHAPES = [
    ["potato"],
    ["potato", "peas"],
    ["potato", "rice"],
    ["peas", "rice", "tomato"],
]
TIMES = [20, 30, 45]


def recipe(number: int, ingredient_ids: Sequence[str], total_minutes: int) -> Recipe:
    return build_recipe(
        id=UUID(int=number),
        name=f"Recipe {number}",
        prep_minutes=0,
        cook_minutes=total_minutes,
        ingredient_ids=ingredient_ids,
        catalog=CATALOG,
    )


def recipes(scored: int, all_staples: int) -> list[Recipe]:
    shapes = cycle(SCORED_SHAPES)
    times = cycle(TIMES)
    made = [recipe(n, next(shapes), next(times)) for n in range(1, scored + 1)]
    made += [
        recipe(n, ["tomato", "salt"], next(times))
        for n in range(1001, 1001 + all_staples)
    ]
    return made


def ids(deck: Deck) -> list[int]:
    return [m.recipe.id.int for m in deck.scored] + [
        m.recipe.id.int for m in deck.all_staples
    ]


def ranked_ids(ranking: Ranking) -> list[int]:
    return [m.recipe.id.int for m in ranking.scored] + [
        m.recipe.id.int for m in ranking.all_staples
    ]


def next_deck(
    pool: Sequence[Recipe],
    cursor: str | None,
    hidden: frozenset[UUID] = frozenset(),
    size: int = MAX_DECK_SIZE,
) -> tuple[Deck, str]:
    """One "generate more" request, the way the service will run it."""
    after = (
        Position() if cursor is None else decode_cursor(cursor, SCOPE, KEYS, now=NOW)
    )
    ranking = rank(pool, PANTRY, SearchFilters(hidden_recipe_ids=hidden))
    deck = build_deck(resume(ranking, after), size)
    return deck, encode_cursor(position_after(deck, after), SCOPE, KEYS, now=NOW)


def walk(pool: Sequence[Recipe], size: int = MAX_DECK_SIZE) -> list[Deck]:
    """Follow the cursors until an empty deck; fail instead of looping forever."""
    decks: list[Deck] = []
    cursor = None
    for _ in range(MAX_PAGES):
        deck, cursor = next_deck(pool, cursor, size=size)
        if not deck.scored and not deck.all_staples:
            return decks
        decks.append(deck)
    raise AssertionError(f"still getting cards after {MAX_PAGES} decks")


# Resume


def test_empty_position_resumes_from_the_start() -> None:
    ranking = rank(recipes(5, 2), PANTRY, SearchFilters())

    assert resume(ranking, Position()) == ranking


def test_resume_starts_strictly_after_the_position() -> None:
    ranking = rank(recipes(5, 3), PANTRY, SearchFilters())
    deck = build_deck(ranking, 3)  # 1 scored + 2 all-staples

    rest = resume(ranking, position_after(deck, Position()))

    assert rest.scored == ranking.scored[1:]
    assert rest.all_staples == ranking.all_staples[2:]


def test_position_keeps_a_tier_the_deck_took_nothing_from() -> None:
    before = Position(all_staples=(20, UUID(int=1001)))
    ranking = rank(recipes(5, 0), PANTRY, SearchFilters())

    after = position_after(build_deck(ranking, MAX_DECK_SIZE), before)

    assert after.all_staples == before.all_staples


# Walking every page


def test_walking_every_page_returns_each_recipe_once_in_rank_order() -> None:
    pool = recipes(45, 7)
    full = rank(pool, PANTRY, SearchFilters())

    decks = walk(pool)

    assert [(len(d.scored), len(d.all_staples)) for d in decks] == [
        (18, 2),
        (18, 2),
        (9, 2),
        (0, 1),
    ]
    shown_scored = [m.recipe.id.int for d in decks for m in d.scored]
    shown_staples = [m.recipe.id.int for d in decks for m in d.all_staples]
    assert shown_scored == [m.recipe.id.int for m in full.scored]
    assert shown_staples == [m.recipe.id.int for m in full.all_staples]


def test_walking_with_small_decks_still_returns_each_recipe_once() -> None:
    pool = recipes(13, 5)
    full = rank(pool, PANTRY, SearchFilters())

    decks = walk(pool, size=3)

    shown = sorted(i for d in decks for i in ids(d))
    assert shown == sorted(ranked_ids(full))


def test_walk_is_the_same_whatever_order_the_recipes_arrive_in() -> None:
    pool = recipes(30, 4)

    assert [ids(d) for d in walk(pool)] == [ids(d) for d in walk(pool[::-1])]


# Hidden recipes between decks (7b.2)


def test_cursor_still_works_when_hidden_grows_between_decks() -> None:
    pool = recipes(40, 0)
    first, cursor = next_deck(pool, None)
    expected_second, _ = next_deck(pool, cursor)
    hide_now = expected_second.scored[3].recipe.id
    swiped_left = frozenset({first.scored[0].recipe.id, hide_now})

    second, _ = next_deck(pool, cursor, hidden=swiped_left)

    assert hide_now.int not in ids(second)
    assert [i for i in ids(expected_second) if i != hide_now.int] == ids(second)[:-1]


def test_hiding_after_every_deck_never_repeats_or_skips_a_recipe() -> None:
    """Left-swipe two cards of every deck, as the app would."""
    pool = recipes(45, 7)
    hidden: frozenset[UUID] = frozenset()
    shown: list[int] = []
    cursor = None
    for _ in range(MAX_PAGES):
        deck, cursor = next_deck(pool, cursor, hidden=hidden)
        if not deck.scored and not deck.all_staples:
            break
        shown += ids(deck)
        hidden |= {UUID(int=i) for i in ids(deck)[:2]}
    else:
        raise AssertionError(f"still getting cards after {MAX_PAGES} decks")

    assert len(shown) == len(set(shown))
    assert sorted(shown) == sorted(ranked_ids(rank(pool, PANTRY, SearchFilters())))
