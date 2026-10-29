# ADR-0007: Postgres ranks and pages the search, using scores Python computed

- Status: Accepted
- Date: 2026-10-29
- Deciders: Nisha
- Supersedes: ADR-0005 rules 5 and 6; the sentence "The database selects candidates but never computes or sorts by the score" in ADR-0003 rule 4
- Related: ADR-0003 (scoring, deck, cursor), ADR-0005 (Postgres, the sync)

## Context

ADR-0005 kept the ranking in Python: SQL returned every candidate recipe, and the domain built, scored and sorted all of them on every request, then showed 20. ADR-0005 rule 6 left Task 3 to measure that on 50,000 recipes and decide.

The Task 3 benchmark (`python -m tests.gate bench`, 30 swipe sessions of up to 3 decks per search, Postgres 16) measured today's code:

| Search | Candidates | p50 ms | p95 ms | p99 ms |
|---|---|---|---|---|
| two rare ingredients | 2,265 | 83 | 143 | 155 |
| vegetarian, 30 minutes | 1,487 | 74 | 113 | 115 |
| two popular ingredients | 14,502 | 566 | 685 | 739 |
| ten ingredients | 34,345 | 1,521 | 1,794 | 1,954 |
| full pantry (50 ingredients) | 45,543 | 2,144 | 2,637 | 2,767 |
| all searches | | 566 | 2,295 | 2,637 |

The cost grows with the number of candidates, not with the 20 cards shown. For the full pantry, `EXPLAIN ANALYZE` puts the query itself at about 0.8 s; the rest of the 2.6 s is moving about 45,000 rows to the app, decoding them, building and ranking them in Python, and serialising the deck. Ranking in SQL with a `LIMIT` removes both the transfer and the Python ranking. Every deck of a swipe session pays it again.

Four ways out were weighed:

- **SQL ranks, looking up scores Python computed (chosen).** A prototype returned the top 20 of the full pantry in about 70 ms.
- **SQL sums the weights, Python sorts.** It returns one narrow row per candidate, so it still grows with the candidates: about 175 ms at 50,000 recipes, and roughly ten times that at 500,000.
- **The formula in SQL too.** It is the second implementation ADR-0005 rejected. Postgres and Python can disagree in the last bit of `log10`, and a one-unit difference in `score_int` silently reorders cards.
- **Cache rankings between decks.** It breaks the stateless server (one pod's cache is not another's), and the first deck is still 2.6 s.

## Decision

**1. Postgres ranks, resumes and limits both tiers.** The search sends the pantry, the filters and the cursor position. Postgres returns at most the deck size plus one recipe per tier, already in ADR-0003 rule 5 order and strictly after the cursor's position in that tier. The extra row only tells whether another deck exists. Deck assembly (ADR-0003 rule 7), the cursor and the response stay in the domain, unchanged.

**2. `score_int` comes from Python, sent with each query.** Each pod computes `scoring.score_int(matched_q, core_q)` once at startup for every `1 <= matched_q <= core_q <= max_core_q`, using its own image's code. It binds that triangle to every ranking query as one `int[]` parameter, and SQL picks the value at index `core_q × (core_q − 1) / 2 + matched_q`. SQL never evaluates the formula; it only adds integers and indexes an array, so ADR-0003 still has one implementation. Each pod ranks with exactly the scores its own code computes, so a deploy that mixes two `SCORING_VERSION`s is correct by construction, with no table to keep in step and no sync needed before new pods start.

`max_core_q` is twice the largest core weight any recipe in the database can reach when the pod starts (its class A and B weights plus 1 for each of its staples, since any staple may be unticked). For the 50,000-recipe gate seed that largest weight is 32, so the triangle has 2,080 values, about 8 KB per query. The headroom covers recipes a later sync adds before the pod restarts.

A storage table (`match_scores`, written by the sync and keyed by `SCORING_VERSION`) was the first draft. It was equally fast and gave the same results, but it needed version rows kept for mid-deploy pods, an app that refused to start without its version's rows, and a sync before every scoring change could deploy.

**3. Two stored weights, recomputed by the sync on every run.**

| Column | Holds |
|---|---|
| `recipe_ingredients.weight` | the ingredient's ADR-0003 weight by class: A = 4, B = 2, staple = 0; NULL until the first sync after the migration |
| `recipes.core_weight` | the sum of `weight` over the recipe's ingredients |

Per request, for each recipe that uses an id in `pantry.have`: `matched_q` = the sum of `weight` over those ids, and `core_q` = `core_weight` + 1 for each of the recipe's ingredients in `pantry.out_of` (an unticked staple counts 1, ADR-0003 rule 1). Recipes with `matched_q` = 0 are not in the scored tier. The all-staples tier keeps its Task 2 query, now sorted by `(total_minutes, id)` and resumed and limited in SQL.

Like `diet` and `all_staples` (ADR-0005 rule 3), these columns derive from the catalog, are written only by the sync, and a test checks them against the domain.

**4. A recipe beyond the triangle is never silently dropped.** If a sync adds a recipe whose core weight is over the pod's `max_core_q` before that pod restarts, the array index is out of range and SQL gets NULL. The query takes `COALESCE(score, -1)`: real scores are 0 or more, so −1 ranks such a recipe last in its tier rather than leaving it out, takes part in the cursor resume like any other value, and fits the cursor's integer key. Rule 5 logs it, since the domain's score is never −1. The restart that follows a sync (ADR-0005) recomputes the triangle.

**5. Python checks the cards it shows.** The service still builds each card's match with `match_recipe` (it needs the matched, missing and assumed lists anyway). If a card's `score_int` differs from the one Postgres sorted by, the service logs an error naming the recipe, the two scores and the catalog hash, and serves the deck. **The card keeps the score Postgres sorted by**, so the cursor position after it (ADR-0003 rule 9) is Postgres's own sort key and the next deck resumes exactly where this one stopped. A mismatch then costs at most a slightly wrong order inside one deck, never a skipped or repeated card. A mismatch means the two sides disagree on weights. Outside the restart window below, that is a bug for a test to catch, not a reason to fail the user's request.

**6. The repository port changes.** `candidates(pantry, filters)` becomes `ranked(pantry, filters, after, limit)`, which returns both tiers' next recipes with their scores. The in-memory adapter implements it with the domain's `rank` and `resume`, and stays the reference: the repository contract tests and a Hypothesis property test (random catalogs, recipes, pantries, filters and cursor walks) require both adapters to return identical decks.

**7. The latency budget, checked in CI.** On the 50,000-recipe gate seed, measured by `python -m tests.gate bench`, `POST /api/v1/recipes/search` must have **p95 at most 200 ms and p99 at most 400 ms for every gate search**, over all its decks. The budget is per search, because a pooled figure drops whenever a cheap search is added; the benchmark's `all searches` row is for information only. CI runs the benchmark in its own job on every pull request and prints the table. Shared runners are noisy, so the job fails only when a search is above twice the budget (p95 over 400 ms or p99 over 800 ms). The plan-shape tests (Task 2 gate) keep guarding the index use that the budget depends on.

## Consequences

- **Easier:** deck time grows far more slowly with the number of matching recipes. Postgres still adds up one integer per matching ingredient row before it can sort, but no recipe leaves the database except the deck's: about 80 ms for the full pantry at 50,000 recipes. A swipe session's later decks cost about the same as its first. At 500,000 recipes this needs another look, for example a statement timeout (Task 4) or a pre-aggregated path.
- **Unchanged for users:** the order, the percentages and the cursor are exactly as before, so `SCORING_VERSION` is not bumped and the web app does not change. The Task 1 and Task 2 gate tests pass unchanged.
- **Harder:** the migration adds the stored weights as nullable columns with no default, and only the sync fills them. The app refuses to start while any recipe has a NULL `core_weight`, the same shape as ADR-0005 rule 7's refusal on an empty `catalog_state`, so the deploy order (migrate, sync, then roll the pods) enforces itself. `scripts/dev.sh` and `docker compose up` already sync after migrating. A scoring change alone needs no sync.
- **Risk:** between a catalog sync that reclassifies an ingredient and the pod restarts that follow it (ADR-0005), Postgres sorts by the new weights while a pod's Python builds cards with its loaded catalog. Rule 5 logs each disagreement and keeps cursors on Postgres's sort key, so the worst case is a misordered card. A pod keeps issuing and accepting cursors under the catalog hash it loaded until it restarts; the restart ends the window and expires those cursors.
- **Deferred:** a statement timeout and pool limits for the worst request (Task 4), and the latency metric on a dashboard (Task 5).
