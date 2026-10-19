"""What the services need from the outside world, as Protocols (ports).

Task 1 runs on the in-memory adapter in recipe_app.infra.memory; Task 2 adds a
Postgres one. Both must pass tests/services/test_repository_contract.py.
"""

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from recipe_app.domain.matching import Pantry
from recipe_app.domain.ranking import SearchFilters
from recipe_app.domain.recipe import Recipe


class RecipeRepository(Protocol):
    async def get(self, recipe_id: UUID) -> Recipe | None:
        """The recipe with this id, or None if there isn't one."""
        ...

    async def candidates(
        self, pantry: Pantry, filters: SearchFilters
    ) -> Sequence[Recipe]:
        """Every recipe the ranking could show for this request, in any order.

        That's every recipe that passes `filters` and either uses an id in
        `pantry.have` or is all staples for this pantry (ADR-0003 rule 3).
        Returning extra recipes is allowed, because ranking filters and
        matches again; leaving one out is a bug, because it never shows.
        """
        ...
