"""What the services need from the outside world, as Protocols (ports).

The adapters are recipe_app.infra.memory (Task 1) and recipe_app.infra.postgres
(Task 2). Both must pass tests/services/test_repository_contract.py.
"""

from typing import Protocol
from uuid import UUID

from recipe_app.domain.cursor import Position
from recipe_app.domain.matching import Pantry
from recipe_app.domain.ranking import Ranking, SearchFilters
from recipe_app.domain.recipe import Recipe


class RecipeRepository(Protocol):
    async def get(self, recipe_id: UUID) -> Recipe | None:
        """The recipe with this id, or None if there isn't one."""
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
