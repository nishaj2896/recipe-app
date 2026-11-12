from uuid import UUID

import pytest

from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.recipe import Recipe, build_recipe
from recipe_app.infra.memory import InMemoryRecipeRepository
from tests.domain.factories import catalog, category, ingredient


def test_duplicate_recipe_id_is_rejected(seed: tuple[Recipe, ...]) -> None:
    with pytest.raises(ValueError, match="duplicate recipe id"):
        InMemoryRecipeRepository([seed[0], seed[0]])


@pytest.mark.anyio
async def test_detail_lists_pairings_in_file_order() -> None:
    one = parse_catalog(catalog(category(), ingredient()))

    def make(n: int, pairs: list[str]) -> Recipe:
        return build_recipe(
            id=UUID(int=n),
            name=f"Potatoes {n}",
            prep_minutes=5,
            cook_minutes=10,
            ingredient_ids=["potato"],
            catalog=one,
            tags={"pairs_with": pairs},
        )

    side_a, side_b = make(2, []), make(3, [])
    main = make(1, [str(side_b.id), str(side_a.id)])

    detail = await InMemoryRecipeRepository([main, side_a, side_b]).detail(main.id)

    assert detail is not None
    assert detail.pairs == (side_b, side_a)
