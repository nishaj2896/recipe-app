"""What the services need from the outside world, as Protocols (ports).

The adapters are recipe_app.infra.memory (Task 1) and recipe_app.infra.postgres
(Task 2). Both must pass tests/services/test_repository_contract.py.
"""

from typing import Protocol
from uuid import UUID

from recipe_app.domain.content import RecipeWithContent
from recipe_app.domain.cursor import Position
from recipe_app.domain.matching import Pantry
from recipe_app.domain.ranking import Ranking, SearchFilters
from recipe_app.domain.recipe_search import Found, RecipeQuery


class StoreUnavailableError(Exception):
    """The store can't answer now: down, unreachable, too slow or out of
    connections. Retrying later may work, so the API answers 503 (ADR-0013
    rule 1). `cause` is safe to log: a kind and a class name, never a message.
    """

    def __init__(self, cause: str) -> None:
        super().__init__(cause)
        self.cause = cause


class RecipeRepository(Protocol):
    async def detail(self, recipe_id: UUID) -> RecipeWithContent | None:
        """The recipe and what a cook needs for it (ADR-0008), or None if there
        isn't one.

        Both come from one version of the recipe: its amounts pair with its
        ingredients by position, so a mix of two versions would pair them wrong.
        """
        ...

    async def ranked(
        self, pantry: Pantry, filters: SearchFilters, after: Position, limit: int
    ) -> Ranking:
        """The first `limit` matches of each tier strictly after `after`.

        Exactly `resume(rank(every recipe, pantry, filters), after)` with each
        tier cut to `limit` (ADR-0003 rules 5, 6 and 9; ADR-0007 rule 1). The
        in-memory adapter computes it that way and is the reference.
        """
        ...

    async def find(self, query: RecipeQuery, limit: int, offset: int) -> Found:
        """Recipes matching typed text, best first (ADR-0012 rule 10).

        Exactly `recipe_search.find(every recipe, query, limit, offset)`;
        the in-memory adapter computes it that way and is the reference.
        """
        ...
