"""Search latency on 50,000 recipes, through the API (the Task 3 gate).

Times `POST /api/v1/recipes/search` in process, so the numbers are server
time: validation, the query, ranking and the JSON body, but no network.
Each round asks for the first deck, then follows the cursor for the next
ones, because a swipe session pays for every deck, not just the first.
"""

import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from recipe_app.api.app import create_app
from recipe_app.domain.cursor import SigningKeys
from recipe_app.infra.catalog_store import read_catalog
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.services.search import RecipeService
from tests.gate.searches import SEARCHES

SEARCH_PATH = "/api/v1/recipes/search"
# Up to three decks per round: one swipe session that keeps asking for more.
DECKS_PER_ROUND = 3
WARMUP_ROUNDS = 3
KEYS = SigningKeys(active_kid="bench", keys={"bench": b"b" * 32})


@dataclass(frozen=True, slots=True)
class Timings:
    """Milliseconds per request for one search, every deck of every round."""

    search: str
    samples: tuple[float, ...]

    @property
    def p50(self) -> float:
        return percentile(self.samples, 50)

    @property
    def p95(self) -> float:
        return percentile(self.samples, 95)

    @property
    def p99(self) -> float:
        return percentile(self.samples, 99)


def percentile(samples: Sequence[float], p: int) -> float:
    """The p-th percentile, interpolated between the two nearest samples."""
    if len(samples) < 2:
        raise ValueError("need at least two samples")
    return statistics.quantiles(samples, n=100, method="inclusive")[p - 1]


async def benchmark(
    engine: AsyncEngine,
    *,
    rounds: int,
    warmup: int = WARMUP_ROUNDS,
    searches: Sequence[str] = tuple(SEARCHES),
) -> list[Timings]:
    """Time each search; the engine's database must hold the gate seed."""
    catalog = await read_catalog(engine)
    service = RecipeService(
        catalog=catalog,
        repository=await PostgresRecipeRepository.open(engine, catalog),
        keys=KEYS,
        clock=lambda: int(time.time()),
    )
    app = create_app(catalog=catalog, service=service)
    async with _client(app) as client:
        results = []
        for name in searches:
            for _ in range(warmup):
                await _round(client, name)
            samples: list[float] = []
            for _ in range(rounds):
                samples += await _round(client, name)
            results.append(Timings(search=name, samples=tuple(samples)))
    return results


def report(results: Sequence[Timings]) -> str:
    width = max(len(result.search) for result in results)
    lines = [
        f"{'search':<{width}}  {'requests':>8}  {'p50 ms':>7}  {'p95 ms':>7}  "
        f"{'p99 ms':>7}"
    ]
    for result in [*results, _all(results)]:
        lines.append(
            f"{result.search:<{width}}  {len(result.samples):>8}  "
            f"{result.p50:>7.1f}  {result.p95:>7.1f}  {result.p99:>7.1f}"
        )
    return "\n".join(lines)


def _all(results: Sequence[Timings]) -> Timings:
    return Timings(
        search="all searches",
        samples=tuple(sample for result in results for sample in result.samples),
    )


async def _round(client: AsyncClient, name: str) -> list[float]:
    """One swipe session: the first deck, then the cursor's decks."""
    body = _body(name)
    samples = []
    for _ in range(DECKS_PER_ROUND):
        started = time.perf_counter()
        response = await client.post(SEARCH_PATH, json=body)
        samples.append((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        cursor = response.json()["next_cursor"]
        if cursor is None:
            break
        body = {**body, "cursor": cursor}
    return samples


def _body(name: str) -> dict[str, Any]:
    search = SEARCHES[name]
    filters = search.filters
    body: dict[str, Any] = {
        "ingredient_ids": search.ingredient_ids,
        "excluded_staples": search.excluded_staples,
    }
    if filters.diet is not None:
        body["diet"] = filters.diet.value
    if filters.max_total_minutes is not None:
        body["max_total_minutes"] = filters.max_total_minutes
    return body


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://bench")
