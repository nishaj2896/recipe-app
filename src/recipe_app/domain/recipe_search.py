"""Finding recipes by what people type (ADR-0012 rule 10).

The in-memory repository ranks with these functions, so they are the
reference the Postgres query is tested against, as ranking.rank is for the
deck (ADR-0007 rule 6). `trigram_similarity` follows pg_trgm's
`similarity()` so the two agree on "a close spelling".
"""

import re
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.normalization import search_key
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.tags import Cuisine

MIN_QUERY_LENGTH, MAX_QUERY_LENGTH = 2, 60
MAX_RESULTS = 20
DEFAULT_RESULTS = 8
# "See all" pages through at most this many results (ADR-0012 rule 11).
MAX_OFFSET = 200
# pg_trgm's default similarity threshold; Postgres compares it as a real.
MIN_SIMILARITY = 0.3
# Shorter keys skip criterion 3: two letters are a start, not a spelling,
# and checking every name for them is the slowest search (ADR-0012 rule 10).
MIN_SPELLING_LENGTH = 3


class Criterion(IntEnum):
    """How a recipe matched, best first (ADR-0012 rule 10)."""

    NAME_STARTS = 1
    WORD_STARTS = 2
    CLOSE_SPELLING = 3
    INGREDIENT_OR_CUISINE = 4


@dataclass(frozen=True, slots=True)
class RecipeQuery:
    """What one search asks for, resolved against the catalog.

    `key` is the typed text as a search key. `ingredient_ids` are the
    ingredients whose name or a search term starts with it, `cuisines` the
    cuisines with a word in their label that does.
    """

    key: str
    ingredient_ids: frozenset[str]
    cuisines: frozenset[Cuisine]


@dataclass(frozen=True, slots=True)
class Found:
    """One page of matches in order, and how many there are in all."""

    recipes: tuple[Recipe, ...]
    total: int


def spells_close(key: str) -> bool:
    """Whether a key is long enough to look for close spellings of it."""
    return len(key) >= MIN_SPELLING_LENGTH


def cuisine_label(cuisine: Cuisine) -> str:
    """The id with spaces, as people type it: "middle eastern", "thai"."""
    return cuisine.value.replace("-", " ")


class QueryResolver:
    """Turns typed text into a RecipeQuery; built once per catalog."""

    def __init__(self, catalog: IngredientCatalog) -> None:
        self._ingredient_keys = tuple(
            (
                item.id,
                frozenset(search_key(text) for text in (item.name, *item.search_terms)),
            )
            for item in catalog.by_id.values()
            if not item.retired
        )

    def resolve(self, text: str) -> RecipeQuery:
        key = search_key(text)
        if not key:
            return RecipeQuery(key="", ingredient_ids=frozenset(), cuisines=frozenset())
        return RecipeQuery(
            key=key,
            ingredient_ids=frozenset(
                ingredient_id
                for ingredient_id, keys in self._ingredient_keys
                if any(k.startswith(key) for k in keys)
            ),
            # Any word of the label: "indian" finds North Indian and the
            # other three, "asian" South Asian and Southeast Asian.
            cuisines=frozenset(
                c for c in Cuisine if _word_starts(cuisine_label(c), key)
            ),
        )


def search_names(recipe: Recipe) -> tuple[str, ...]:
    """The recipe's name, then its aliases, as search keys; the sync stores
    these, in this order, for Postgres to search.
    """
    return tuple(search_key(text) for text in (recipe.name, *recipe.tags.also_known_as))


def match(recipe: Recipe, query: RecipeQuery) -> tuple[Criterion, float] | None:
    """The recipe's best criterion and, for a close spelling, its best
    similarity; None when it doesn't match.
    """
    if not query.key:
        return None
    names = search_names(recipe)
    if names[0].startswith(query.key):
        return Criterion.NAME_STARTS, 0.0
    if any(_word_starts(name, query.key) for name in names):
        return Criterion.WORD_STARTS, 0.0
    similarity = (
        max(trigram_similarity(name, query.key) for name in names)
        if spells_close(query.key)
        else 0.0
    )
    if spells_close(query.key) and similarity >= _real(MIN_SIMILARITY):
        return Criterion.CLOSE_SPELLING, similarity
    if recipe.tags.cuisine in query.cuisines or any(
        item.id in query.ingredient_ids for item in recipe.ingredients
    ):
        return Criterion.INGREDIENT_OR_CUISINE, 0.0
    return None


def find(
    recipes: Iterable[Recipe], query: RecipeQuery, limit: int, offset: int
) -> Found:
    """Every match in order: criterion, then similarity (highest first),
    then name as a search key (code point order, Postgres's "C" collation),
    then id; then the page asked for.
    """
    matches = []
    for recipe in recipes:
        found = match(recipe, query)
        if found is not None:
            criterion, similarity = found
            key = (criterion, -similarity, search_names(recipe)[0], recipe.id)
            matches.append((key, recipe))
    matches.sort(key=lambda pair: pair[0])
    page = tuple(recipe for _, recipe in matches[offset : offset + limit])
    return Found(recipes=page, total=len(matches))


def trigram_similarity(a: str, b: str) -> float:
    """pg_trgm's similarity(): shared trigrams over all trigrams, as a real.

    Each run of letters and digits is a word, padded with two spaces in
    front and one behind, and every three characters in a row is a trigram.
    """
    first, second = _trigrams(a), _trigrams(b)
    if not first or not second:
        return 0.0
    shared = len(first & second)
    return _real(shared / (len(first) + len(second) - shared))


def _trigrams(text: str) -> frozenset[str]:
    found: set[str] = set()
    for word in re.findall(r"[^\W_]+", text.lower()):
        padded = f"  {word} "
        found.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return frozenset(found)


def _word_starts(name: str, key: str) -> bool:
    return name.startswith(key) or f" {key}" in name


def _real(value: float) -> float:
    """Rounded to a 4-byte float, as Postgres's real type holds it."""
    rounded: float = struct.unpack("f", struct.pack("f", value))[0]
    return rounded
