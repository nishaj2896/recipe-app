# ADR-0005: Recipes and the catalog live in PostgreSQL, loaded from the reviewed data files

- Status: Accepted
- Date: 2026-10-19
- Amended: 2026-10-29 (rules 5 and 6 superseded by ADR-0007: Postgres ranks and pages the search)
- Deciders: Nisha
- Related: ADR-0001 (append-only ids), ADR-0002 rule 7 (catalog as data), ADR-0003 (scoring, cursor)

## Context

Task 1 serves recipes from an in-memory repository built from `data/recipes.v1.toml` at startup. That stops working once the recipe set grows past what every pod should hold in memory and parse on boot (Task 3 measures 50,000 recipes), and it ties every recipe change to a new deploy. Task 2 moves the data into PostgreSQL behind the existing `RecipeRepository` port.

Three things constrain the design:

- The data files are reviewed in pull requests and checked in CI (ADR-0002 rule 7). That review is the only quality gate the catalog has, so it must stay.
- Ranking (ADR-0003) is a weighted, per-request score with exact integer sort keys. Two implementations of it, one in Python and one in SQL, would drift, and a drift silently changes what users see.
- Cursors carry the catalog's `content_hash` (ADR-0003 rule 9). Whatever the app loads must have the same hash on every pod, or a cursor minted on one pod fails on another.

## Decision

**1. PostgreSQL is the runtime store for the catalog and the recipes.** The server reads only the database; it no longer needs the data files at runtime. The supported floor is PostgreSQL 16; CI and the local compose file pin 17.

**2. The TOML files stay the source of truth.** A sync command (`recipe-app db sync`) parses both files with the existing domain loaders, so every Task 1 check still runs, then writes them to the database in one transaction. It is the only writer. It is idempotent, takes an advisory lock so two runs can't interleave, and refuses to delete or re-key a category, ingredient or recipe that is already in the database (ADR-0001 rule 2): retire it in the file instead. It stores the catalog's `content_hash` with the data.

**3. Schema, owned by Alembic migrations.**

| Table | Holds | Notes |
|---|---|---|
| `categories` | id, name, position, retired | |
| `ingredients` | id, name, class, kind, diet, category, retired | `class`, `kind`, `diet` are `text` with `CHECK` constraints, not Postgres enums, so adding a value is a one-line migration |
| `ingredient_search_terms` | ingredient, position, normalized term | |
| `recipes` | id (uuid), name, prep and cook minutes, diet, all_staples | `total_minutes` is a generated column; nobody writes it |
| `recipe_ingredients` | recipe, position, ingredient | primary key (recipe, position); unique (recipe, ingredient); index (ingredient, recipe) for the search |
| `catalog_state` | one row: catalog `content_hash`, sync time | |

`recipes.diet` and `recipes.all_staples` are derived from the catalog (ADR-0002 rule 6, ADR-0003 rule 3). They are stored so the search can filter on them without joining every ingredient, and the sync recomputes them for every recipe on every run with the domain's own code. Because the sync is the only writer and the catalog changes only through it, they can't go stale. A test checks the stored values against the domain.

Migrations are hand-reviewed (autogenerate only drafts them), every one has a working downgrade, and a test fails when the SQLAlchemy table definitions and the migrations disagree. Migrations and the sync run as their own commands, never on app startup, so one deploy step owns schema changes and pods never race to apply them.

**4. SQLAlchemy 2 Core with asyncpg, not the ORM.** The domain types are frozen dataclasses built by validating constructors. The repository maps rows to them explicitly; there is no second, mutable model of a recipe to keep in step.

**5. Scoring stays in Python; SQL finds the candidates.** _Superseded by ADR-0007, which measured this on 50,000 recipes._ `candidates()` is one indexed query: recipes that use any ingredient in `pantry.have`, plus all-staples recipes that use no unticked staple, after the diet, time and hidden-id filters. The domain then ranks them exactly as it does today, so ADR-0003 has one implementation. The repository contract tests run against both adapters and compare their results.

**6. The deck resume stays in the domain for now.** _Superseded by ADR-0007._ Doing the keyset resume in SQL would mean computing `score_int` in SQL, which is the second implementation rule 5 avoids. Task 3 measures p95 latency on 50,000 recipes; if fetching and ranking the candidates misses the budget there, a later ADR decides how to push ranking down (for example a stored per-recipe weight total) with those numbers in hand.

**7. The app loads the catalog from the database once at startup** and refuses to start if `catalog_state` is empty. A catalog change reaches running pods on their next restart, which the deploy after a sync does anyway. The connection pool opens and closes with the app's lifespan.

## Consequences

- **Easier:** recipes can grow without growing every pod's memory or startup time, and recipe changes no longer need a code deploy, only a sync. The container image (Task 6) no longer needs the data files.
- **Harder:** tests that touch the database need a PostgreSQL server. They read `TEST_DATABASE_URL`, create a throwaway database per test session, and skip when it isn't set; CI always sets it, and fails if it doesn't.
- **Risk:** a sync that runs while old pods are serving changes the data under their loaded catalog until they restart. Their cursors keep working, because each pod checks cursors against the catalog it loaded, but a pod may rank with an ingredient's old class, and it skips (and logs) any recipe that uses an ingredient it hasn't loaded rather than failing the request. Restarting pods after every sync ends the window; the deploy runbook (Task 10) makes it one step.
- **Deferred:** SQL-side ranking and keyset resume (Task 3, rule 6), connection timeouts and retries (Task 4), readiness that checks the database (Task 5), backup and restore (Task 10).
