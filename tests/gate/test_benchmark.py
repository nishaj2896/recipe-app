"""The Task 3 benchmark's own checks: its maths, its searches, and that it runs."""

import pytest

from recipe_app.api.schemas import MAX_INGREDIENT_IDS
from recipe_app.domain.catalog import IngredientCatalog, IngredientClass
from recipe_app.infra.database import create_engine
from tests.gate.benchmark import DECKS_PER_ROUND, benchmark, percentile, report
from tests.gate.searches import FULL_PANTRY


def test_percentile_interpolates_between_samples() -> None:
    samples = [float(n) for n in range(1, 101)]

    assert percentile(samples, 50) == pytest.approx(50.5)
    assert percentile(samples, 95) == pytest.approx(95.05)
    assert percentile(samples, 99) == pytest.approx(99.01)


def test_percentile_needs_two_samples() -> None:
    with pytest.raises(ValueError, match="two samples"):
        percentile([1.0], 95)


def test_the_full_pantry_is_the_largest_the_api_accepts(
    real_catalog: IngredientCatalog,
) -> None:
    """Every id must count: a staple or a retired id would shrink the search."""
    assert len(set(FULL_PANTRY)) == len(FULL_PANTRY) == MAX_INGREDIENT_IDS
    for ingredient_id in FULL_PANTRY:
        ingredient = real_catalog.by_id[ingredient_id]
        assert not ingredient.retired
        assert ingredient.ingredient_class is not IngredientClass.STAPLE


@pytest.mark.anyio
async def test_the_benchmark_runs_against_the_gate_database(
    gate_database_url: str,
) -> None:
    engine = create_engine(gate_database_url)
    try:
        [result] = await benchmark(
            engine, rounds=2, warmup=0, searches=["two rare ingredients"]
        )
    finally:
        await engine.dispose()

    assert result.search == "two rare ingredients"
    assert len(result.samples) == 2 * DECKS_PER_ROUND
    assert all(sample > 0 for sample in result.samples)
    assert "two rare ingredients" in report([result])
