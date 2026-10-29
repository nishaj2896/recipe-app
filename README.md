# Pantry-to-Plate

Tell it what's in your kitchen, and it shows you what you can cook.

Pantry-to-Plate is a recipe recommendation API. You pick the ingredients you have from a catalog. The API returns a deck of recipe cards, ranked by how much of each recipe you can already make. Household staples like salt, oil and spices are assumed, so you never have to tick them.

> **Status: early development.** The `v1` API runs on an in-memory seed of hand-picked recipes. A database comes next. See [Roadmap](#roadmap).

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
| Web app | React 19, TypeScript (strict), Vite, Vitest, ESLint, Prettier, Node 22 ([ADR-0006](docs/adr/0006-frontend-web-app.md)) |

## Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/). It installs the pinned Python version for you.

```bash
git clone https://github.com/nishaj2896/recipe-app.git
cd recipe-app
uv sync --locked             # create .venv and install exactly what uv.lock pins; fails if the lock is stale
uv run pre-commit install    # run the checks on every commit
uv run pytest                # should pass
```

## Running the whole app

With [Docker Desktop](https://www.docker.com/products/docker-desktop/) running, uv and Node 22 installed, one command runs everything:

```bash
scripts/dev.sh               # add --host to open it from a phone on the same Wi-Fi
```

It starts the database, applies the migrations, loads the data files, then serves the API on <http://127.0.0.1:8000> and the web app on <http://localhost:5173>. Ctrl+C stops both servers; `docker compose down` stops the database. On its first run it writes a git-ignored `.env` from [`.env.example`](.env.example) with a new signing key, and other commands can read it too: `uv run --env-file .env recipe-app db sync`. The sections below do the same steps by hand.

## Running the API

The API reads recipes and the ingredient catalog from PostgreSQL, so start the local database, create the tables and load the data files first:

```bash
docker compose up -d --wait
export DATABASE_URL=postgresql+asyncpg://recipe_app:recipe_app@localhost:5433/recipe_app
uv run alembic upgrade head
uv run recipe-app db sync
```

It also signs its "generate more" cursors, so it needs a signing key before it starts. For local use, make a throwaway one:

```bash
export CURSOR_ACTIVE_KID=dev
export CURSOR_SIGNING_KEYS="{\"dev\": \"$(uv run python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')\"}"
uv run recipe-app            # or: uv run uvicorn --factory recipe_app.api.app:build_app --reload
```

Then open <http://127.0.0.1:8000/docs> and try `POST /api/v1/recipes/search` with `{"ingredient_ids": ["potato", "peas"]}`.

| Variable | Meaning |
|---|---|
| `CURSOR_SIGNING_KEYS` | JSON object of key id to a base64url key of at least 32 bytes. Every key verifies cursors |
| `CURSOR_ACTIVE_KID` | The key id that signs new cursors |
| `DATABASE_URL` | `postgresql+asyncpg://` URL of the database the sync filled |
| `RECIPE_APP_DATA_DIR` | Folder with `ingredients.v1.toml` and `recipes.v1.toml` (default `./data`); only `recipe-app db sync` reads it |

The app refuses to start if a key is missing or too short, if `DATABASE_URL` is missing, or if the database has never been synced. It loads the catalog once at startup, so after a sync, restart the app to pick up the new catalog. In production the keys come from the secret store, never from the repo or the logs.

| Endpoint | What it does |
|---|---|
| `POST /api/v1/recipes/search` | One swipe deck for a pantry, with filters and a `next_cursor` |
| `GET /api/v1/recipes/{id}` | One recipe |
| `GET /api/v1/ingredients` | The ingredient catalog for the picker (ETag, `304` when unchanged) |
| `GET /api/v1/staples` | Staples grouped by kind and category (ETag, `304` when unchanged) |
| `GET /healthz` | Liveness |

Every error is an [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) `application/problem+json` body. A stale cursor returns `422` with type `/problems/cursor-expired`: search again without a cursor.

## Development

| Task | Command |
|---|---|
| Run the tests | `uv run pytest` |
| Run only the API contract (the Task 1 gate) | `uv run pytest tests/contract -v` |
| Run only the query-plan checks on 50,000 recipes (the Task 2 gate) | `uv run pytest tests/gate -v` (needs `TEST_DATABASE_URL`) |
| Print the search's query plans to read them | `uv run python -m tests.gate load`, then `uv run python -m tests.gate explain` (needs `DATABASE_URL` of an empty, migrated throwaway database) |
| Lint | `uv run ruff check` |
| Format | `uv run ruff format` |
| Type check | `uv run mypy` |
| Run every pre-commit check | `uv run pre-commit run --all-files` |
| Add a dependency | `uv add <package>` (or `uv add --dev <package>`) |
| Start the local database | `docker compose up -d --wait` |
| Stop it (keeps the data) | `docker compose down` |
| Wipe it | `docker compose down -v` |
| Apply migrations | `uv run alembic upgrade head` (needs `DATABASE_URL`) |
| Load the data files into the database | `uv run recipe-app db sync` (needs `DATABASE_URL`) |
| New migration (a draft: read it before committing) | `uv run alembic revision --autogenerate -m "<what changed>"` |
| Run the database tests | `TEST_DATABASE_URL=postgresql+asyncpg://recipe_app:recipe_app@localhost:5433/recipe_app uv run pytest` |

Point the app at it with `DATABASE_URL=postgresql+asyncpg://recipe_app:recipe_app@localhost:5433/recipe_app`.

Tool settings live in `pyproject.toml`. mypy runs in strict mode, and pytest treats warnings as errors.

### Web app

The web app lives in `web/`. Run these from that folder, after `npm ci`:

| Task | Command |
|---|---|
| Start it (proxies `/api` to the API on `:8000`; set `API_URL` to change) | `npm run dev` |
| Run the tests | `npm test` |
| Lint, type check, check formatting | `npm run lint`, `npm run typecheck`, `npm run format:check` |
| Regenerate the API types after changing the API | `npm run api:generate` (commit `openapi.json` and `src/api/schema.d.ts`) |
| Build for production | `npm run build` |
| Install the browser the end-to-end tests use (once) | `npx playwright install --with-deps chromium` |
| Run the end-to-end, accessibility and motion tests (the frontend gate) | `npm run e2e` (needs `DATABASE_URL` of a migrated, synced database; starts the API and the built app itself) |

## Project layout

```text
src/recipe_app/
├── domain/      # pure business rules: normalization, staples, scoring. No I/O, no framework.
├── services/    # use cases that combine the domain with data access
├── infra/       # adapters: data files, and later the database
└── api/         # FastAPI routers and request/response schemas
tests/           # mirrors src/; tests/contract drives the API end to end over HTTP,
                 # tests/gate checks the search's query plans on 50,000 recipes
docs/adr/        # architecture decision records
web/             # the web app (React); src/api/schema.d.ts is generated from web/openapi.json
```

Dependencies point inward: `api` → `services` → `domain`, with `infra` plugged in behind interfaces. The domain never imports FastAPI or a database driver, so the core rules can be tested without HTTP, and swapping storage later doesn't touch them.

## Architecture decisions

Decisions that would be expensive to reverse are recorded as ADRs in [`docs/adr/`](docs/adr/):

- [ADR-0001](docs/adr/0001-ingredient-normalization.md): users pick ingredients from a catalog by id, and normalization applies only to catalog data and search
- [ADR-0002](docs/adr/0002-household-staples.md): ingredient classes and household staples are server-owned catalog data
- [ADR-0003](docs/adr/0003-weighted-match-scoring.md): recipes are ranked by a weighted, size-aware score with a deterministic integer sort key
- [ADR-0004](docs/adr/0004-coconut-category-rule.md): coconut products are filed by what they are used as
- [ADR-0005](docs/adr/0005-postgres-persistence.md): recipes and the catalog live in PostgreSQL, loaded from the reviewed data files
- [ADR-0006](docs/adr/0006-frontend-web-app.md): the frontend is a mobile-first web app in `web/`, on the same origin as the API

To change one of these decisions, add a new ADR that supersedes it rather than rewriting the old one.

## Roadmap

- [x] Project foundation: uv, Ruff, mypy strict, pytest, pre-commit
- [x] Design decisions (ADR-0001 to ADR-0003)
- [x] Ingredient normalization
- [x] Ingredient catalog and staples as data
- [x] Domain entities: ingredients, recipes, computed diet
- [x] Matching and ranking engine
- [x] Deck assembly and signed cursor
- [x] Repository interface with an in-memory seed
- [x] Service layer
- [x] HTTP API (`/api/v1`) with RFC 9457 errors
- [x] Contract tests for the Task 1 verification gate
- [x] PostgreSQL persistence, checked on 50,000 recipes (the Task 2 gate)

Later: Docker, Kubernetes.

## Contributing

- Create one branch per change from an up-to-date `main`.
- Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/), for example `feat(domain): add ingredient normalization`.
- Open a pull request. The pre-commit checks and the tests must pass.
- PRs are squash-merged, so `main` gets one clean commit per change.
