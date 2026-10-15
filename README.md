# Pantry-to-Plate

Tell it what's in your kitchen, and it shows you what you can cook.

Pantry-to-Plate is a recipe recommendation API. You pick the ingredients you have from a catalog. The API returns a deck of recipe cards, ranked by how much of each recipe you can already make. Household staples like salt, oil and spices are assumed, so you never have to tick them.

> **Status: early development.** The project foundation and the design decisions are done. The domain logic and the HTTP API are being built step by step, so there are no endpoints to call yet. See [Roadmap](#roadmap).

## How it works

1. **Pick, don't type.** The app downloads the ingredient catalog and you tick what you have. Requests carry stable ingredient ids, never free text, so there are no spelling or plural mismatches ([ADR-0001](docs/adr/0001-ingredient-normalization.md)).
2. **Staples are assumed.** Every ingredient has a class: core, supporting, aromatic or staple. Staples count as available unless you say you're out of one ([ADR-0002](docs/adr/0002-household-staples.md)).
3. **Recipes are ranked by a weighted, size-aware score.** A nearly complete curry ranks above a one-ingredient dish you can fully make, and a missing main ingredient costs more than a missing spice. Ties are broken by total cooking time, then by recipe id, so the same request always gives the same order ([ADR-0003](docs/adr/0003-weighted-match-scoring.md)).
4. **Swipe through decks.** Results come in decks of up to 20 cards and are paged with a signed cursor. You can filter by diet (vegan, vegetarian, egg, non-veg) and by maximum total time.

## Tech stack

| | |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI, Pydantic v2, Uvicorn |
| Packaging | [uv](https://docs.astral.sh/uv/), with a committed `uv.lock` |
| Quality | Ruff (lint and format), mypy (strict), pytest, pre-commit |

## Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/). It installs the pinned Python version for you.

```bash
git clone https://github.com/nishaj2896/recipe-app.git
cd recipe-app
uv sync --locked             # create .venv and install exactly what uv.lock pins; fails if the lock is stale
uv run pre-commit install    # run the checks on every commit
uv run pytest                # should pass
