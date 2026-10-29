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

- **SQL ranks, looking scores up in a table Python wrote (chosen).** A prototype returned the top 20 of the full pantry in about 70 ms.
- **SQL sums the weights, Python sorts.** It returns one narrow row per candidate, so it still grows with the candidates: about 175 ms at 50,000 recipes, and roughly ten times that at 500,000.
- **The formula in SQL too.** It is the second implementation ADR-0005 rejected. Postgres and Python can disagree in the last bit of `log10`, and a one-unit difference in `score_int` silently reorders cards.
- **Cache rankings between decks.** It breaks the stateless server (one pod's cache is not another's), and the first deck is still 2.6 s.

## Decision

**1. Postgres ranks, resumes and limits both tiers.** The search sends the pantry, the filters and the cursor position. Postgres returns at most the deck size plus one recipe per tier, already in ADR-0003 rule 5 order and strictly after the cursor's position in that tier. The extra row only tells whether another deck exists. Deck assembly (ADR-0003 rule 7), the cursor and the response stay in the domain, unchanged.

**2. `score_int` comes from a table, and only Python fills it.** `match_scores(scoring_version, matched_q, core_q, score_int)`, primary key `(scoring_version, matched_q, core_q)`, holds the value of `scoring.score_int(matched_q, core_q)` for every `1 <= matched_q <= core_q <= max_core_q`. `max_core_q` is the largest core weight any synced recipe can reach: its class A and B weights plus 1 for each of its staples, since any staple may be unticked. For the seed recipes that is 24, or 300 rows; for the 50,000-recipe gate seed, 32, or 528 rows. The SQL never evaluates the formula; it only adds integers and joins. ADR-0003 still has one implementation.

**3. Two stored weights, recomputed by the sync on every run.**

| Column | Holds |
|---|---|
| `recipe_ingredients.weight` | the ingredient's ADR-0003 weight by class: A = 4, B = 2, staple = 0 |
| `recipes.core_weight` | the sum of `weight` over the recipe's ingredients |

Per request, for each recipe that uses an id in `pantry.have`: `matched_q` = the sum of `weight` over those ids, and `core_q` = `core_weight` + 1 for each of the recipe's ingredients in `pantry.out_of` (an unticked staple counts 1, ADR-0003 rule 1). Recipes with `matched_q` = 0 are not in the scored tier. The all-staples tier keeps its Task 2 query, now sorted by `(total_minutes, id)` and resumed and limited in SQL.

Like `diet` and `all_staples` (ADR-0005 rule 3), these columns derive from the catalog, are written only by the sync, and a test checks them against the domain.

**4. The sync writes `match_scores`; versions live side by side.** The sync writes the rows for the `SCORING_VERSION` it was built with and keeps the rows of the version before it, so pods still running the previous image keep ranking during a deploy. It deletes older versions. The app refuses to start when `match_scores` has no rows for its own `SCORING_VERSION`. A scoring change therefore deploys in the existing order: migrate, sync, then roll the pods.

**5. Python checks the cards it shows.** The service still builds each card's match with `match_recipe` (it needs the matched, missing and assumed lists anyway). If a card's `score_int` differs from the one Postgres sorted by, the service logs an error naming the recipe, the two scores and the catalog hash, and serves the deck. A mismatch means the two sides disagree on weights. Outside the restart window below, that is a bug for a test to catch, not a reason to fail the user's request.

**6. The repository port changes.** `candidates(pantry, filters)` becomes `ranked(pantry, filters, after, limit)`, which returns both tiers' next recipes with their scores. The in-memory adapter implements it with the domain's `rank` and `resume`, and stays the reference: the repository contract tests and a Hypothesis property test (random catalogs, recipes, pantries, filters and cursor walks) require both adapters to return identical decks.

**7. The latency budget, checked in CI.** On the 50,000-recipe gate seed, measured by `python -m tests.gate bench`, `POST /api/v1/recipes/search` must have **p95 at most 200 ms and p99 at most 400 ms for every gate search**, over all its decks. The budget is per search, because a pooled figure drops whenever a cheap search is added; the benchmark's `all searches` row is for information only. CI runs the benchmark in its own job on every pull request and prints the table. Shared runners are noisy, so the job fails only when a search is above twice the budget (p95 over 400 ms or p99 over 800 ms). The plan-shape tests (Task 2 gate) keep guarding the index use that the budget depends on.

## Consequences

- **Easier:** deck time no longer grows with the number of matching recipes, so broad pantries and a larger recipe set stay fast. A swipe session's later decks cost the same as its first.
- **Unchanged for users:** the order, the percentages and the cursor are exactly as before, so `SCORING_VERSION` is not bumped and the web app does not change. The Task 1 and Task 2 gate tests pass unchanged.
- **Harder:** a scoring change now needs a sync before new pods start, and the app refuses to start without it. `scripts/dev.sh` and `docker compose up` already sync first; the deploy runbook (Task 10) keeps that order.
- **Risk:** between a catalog sync that reclassifies an ingredient and the pod restarts that follow it (ADR-0005), Postgres sorts by the new weights while a pod's Python builds cards with its loaded catalog. Rule 5 logs each disagreement, and cursors already expire on a catalog change. The restart ends the window.
- **Risk:** a recipe whose `core_q` has no row in `match_scores` would silently drop out of the scored tier. The sync writes the weights and the table in one transaction, sized from the same recipes, and a test checks that every reachable `core_q` has a row.
- **Deferred:** a statement timeout and pool limits for the worst request (Task 4), and the latency metric on a dashboard (Task 5).
