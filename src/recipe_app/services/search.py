"""The search use case: one "generate more" request, end to end (ADR-0003)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from recipe_app.domain.catalog import Diet, IngredientCatalog
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
from recipe_app.domain.matching import Ignored, resolve_pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.scoring import SCORING_VERSION
from recipe_app.services.ports import RecipeRepository


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """A search request, already bounded and typed by the API layer."""

    ingredient_ids: Sequence[str]
    excluded_staples: Sequence[str] = ()
    diet: Diet | None = None
    max_total_minutes: int | None = None
    hidden_recipe_ids: frozenset[UUID] = field(default_factory=frozenset)
    limit: int = MAX_DECK_SIZE
    cursor: str | None = None

    def __post_init__(self) -> None:
        # Here, not in build_deck, so a bad limit fails before any I/O.
        if not 1 <= self.limit <= MAX_DECK_SIZE:
            raise ValueError(f"need 1 <= limit <= {MAX_DECK_SIZE}, got {self.limit}")


@dataclass(frozen=True, slots=True)
class SearchResult:
    deck: Deck
    ignored: tuple[Ignored, ...]
    next_cursor: str | None


class RecipeService:
    """Glues the domain to a repository; the clock and keys are injected."""

    def __init__(
        self,
        *,
        catalog: IngredientCatalog,
        repository: RecipeRepository,
        keys: SigningKeys,
        clock: Callable[[], int],
    ) -> None:
        self._catalog = catalog
        self._repository = repository
        self._keys = keys
        self._clock = clock

    async def get_recipe(self, recipe_id: UUID) -> Recipe | None:
        return await self._repository.get(recipe_id)

    async def search(self, query: SearchQuery) -> SearchResult:
        """Raises PantryError, InvalidCursorError or ExpiredCursorError."""
        now = self._clock()
        scope = Scope(
            catalog=self._catalog.content_hash,
            scoring=SCORING_VERSION,
            req=request_fingerprint(
                diet=query.diet,
                max_total_minutes=query.max_total_minutes,
                ingredient_ids=query.ingredient_ids,
                excluded_staples=query.excluded_staples,
            ),
        )
        # The cursor first: it is the cheapest check and the likeliest to fail.
        before = (
            Position()
            if query.cursor is None
            else decode_cursor(query.cursor, scope, self._keys, now=now)
        )
        pantry = resolve_pantry(
            ingredient_ids=query.ingredient_ids,
            excluded_staples=query.excluded_staples,
            catalog=self._catalog,
        )
        filters = SearchFilters(
            diet=query.diet,
            max_total_minutes=query.max_total_minutes,
            hidden_recipe_ids=query.hidden_recipe_ids,
        )

        # One more than a deck per tier: the extra one says whether a next deck exists.
        remaining = await self._repository.ranked(
            pantry, filters, before, query.limit + 1
        )
        deck = build_deck(remaining, query.limit)
        after = position_after(deck, before)
        rest = resume(remaining, after)
        next_cursor = (
            encode_cursor(after, scope, self._keys, now=now)
            if rest.scored or rest.all_staples
            else None
        )
        return SearchResult(deck=deck, ignored=pantry.ignored, next_cursor=next_cursor)
