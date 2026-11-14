"""The search use case: one "generate more" request, end to end (ADR-0003)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from recipe_app.domain.catalog import Diet, IngredientCatalog
from recipe_app.domain.content import RecipeWithContent
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
from recipe_app.domain.matching import Ignored, PantryError, resolve_pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe_search import Found, QueryResolver
from recipe_app.domain.scoring import SCORING_VERSION
from recipe_app.domain.tags import Allergen, Course, Mood, Weather
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
    min_total_minutes: int | None = None
    jain: bool = False
    avoid_allergens: frozenset[Allergen] = field(default_factory=frozenset)
    avoid_ingredient_ids: frozenset[str] = field(default_factory=frozenset)
    courses: frozenset[Course] = field(default_factory=frozenset)
    moods: frozenset[Mood] = field(default_factory=frozenset)
    weather: frozenset[Weather] = field(default_factory=frozenset)

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
        self._resolver = QueryResolver(catalog)

    async def get_detail(self, recipe_id: UUID) -> RecipeWithContent | None:
        return await self._repository.detail(recipe_id)

    async def find(self, text: str, *, limit: int, offset: int) -> Found:
        """Recipe search by name, alias, ingredient or cuisine (ADR-0012 rule
        10). Food rules don't apply: the app marks what breaks them.
        """
        return await self._repository.find(self._resolver.resolve(text), limit, offset)

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
                min_total_minutes=query.min_total_minutes,
                jain=query.jain,
                avoid_allergens=query.avoid_allergens,
                avoid_ingredient_ids=query.avoid_ingredient_ids,
                courses=query.courses,
                moods=query.moods,
                weather=query.weather,
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
        self._check_avoided(query.avoid_ingredient_ids)
        filters = SearchFilters(
            diet=query.diet,
            max_total_minutes=query.max_total_minutes,
            min_total_minutes=query.min_total_minutes,
            hidden_recipe_ids=query.hidden_recipe_ids,
            jain=query.jain,
            avoid_allergens=query.avoid_allergens,
            avoid_ingredient_ids=query.avoid_ingredient_ids,
            courses=query.courses,
            moods=query.moods,
            weather=query.weather,
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

    def _check_avoided(self, ingredient_ids: frozenset[str]) -> None:
        """Every id to avoid was published once; a retired one is fine to avoid,
        since no live recipe uses it.
        """
        unknown = sorted(i for i in ingredient_ids if i not in self._catalog.by_id)
        if unknown:
            raise PantryError(
                [f"avoid_ingredient_ids: unknown ingredient {i!r}" for i in unknown]
            )
