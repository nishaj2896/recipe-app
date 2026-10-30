# ADR-0003: Recipes are ranked by a weighted, size-aware score with a deterministic integer sort key

- Status: Accepted
- Date: 2026-10-15
- Amended: 2026-10-18 (recipe times: rule 10)
- Amended: 2026-10-19 (deck mix and deck sizes: rule 7; cursor `req`: rule 9)
- Amended: 2026-10-29 (rule 4: Postgres sorts by `score_int`, looked up from values this function computed; ADR-0007)
- Deciders: Nisha
- Supersedes: the "Result shape" ranking rule, the plain match-percentage definition, and the "fresh staple typed is promoted to core" rule in the Task 1 "Product decisions locked" table
- Related: ADR-0001, ADR-0002

## Context

The original v1 rule ranked by plain match % over core ingredients: matched ÷ core. That rule has a "potato trap". A one-ingredient dish you can cook scores 100% and sits above a nearly complete ten-ingredient curry. It also treats a missing chilli the same as a missing kilo of paneer. Ingredients matter unequally, and users prefer complete, substantial dishes. Whatever replaces the rule must stay deterministic for cursor pagination, must never divide by zero, and must stay explainable on the card.

## Decision

**1. Weights come from the ingredient class (ADR-0002) and are integers in quarter units:** A = 4, B = 2, an unticked staple = 1, a ticked staple = not counted. The weights shown to people (1.0, 0.5, 0.25 in ADR-0002) are these values ÷ 4. Integer sums are exact and don't depend on the order ingredients are added up, so the same recipe scores the same on every pod. The constants live in one domain module.

**2. For each candidate recipe r and this request:**
- `core(r)` = every class A and B ingredient of r, plus every staple of r that is in `excluded_staples` (at weight 1).
- `assumed(r)` = every other staple of r, returned as `assumed_staples`.
- `effective_ids` = `ingredient_ids` minus every id that is retired or now class S (ADR-0001 rule 3). `matched(r)` = `core(r)` ∩ `effective_ids`. `missing(r)` = `core(r)` − `effective_ids`.

A staple never counts as matched. A staple id in `ingredient_ids` is either rejected, if it was never published, or treated as an assumed staple (ADR-0001 rule 3). If the same staple is also in `excluded_staples`, the exclusion wins, because the user said they're out of it. So an excluded staple in a recipe is always missing.

**3. Two tiers:**
- **Scored tier:** `matched(r)` is not empty. At least one ticked ingredient appears in the recipe.
- **All-staples tier:** `core(r)` is empty for this request: the recipe uses only staples, and none of them are excluded. These recipes get no score, so no division happens.
- A recipe with a non-empty core and no matches is not shown.

**4. The score, for the scored tier only:**

```
matched_q   = Σ W(matched)                               # integer, quarter units
core_q      = Σ W(core)                                  # integer > 0
match_ratio = Fraction(matched_q, core_q)                # exact; 0 < match_ratio ≤ 1
composite   = float(match_ratio) × log10(matched_q / 4 + 1)
score_int   = round(composite × 1_000_000)               # the only value used for sorting
```

`score_int` is computed in exactly one pure function in `recipe_app.domain.scoring`. The database never computes the score. Since ADR-0007 it sorts by `score_int` values this function computed, which each pod sends with the query. Only `log10` is a float. Every pod runs the same image, and the gate tests pin exact `score_int` values (the potato trap is 571561 against 301030), so a change in floating-point behaviour fails a test rather than silently reordering results.

**5. The sort key is a total order:**
- Scored tier: `(-score_int, total_minutes, recipe_id)`, where `total_minutes = prep_minutes + cook_minutes`.
- All-staples tier: `(total_minutes, recipe_id)`.

**6. Filters run before ranking and deck assembly:** `diet`, `max_total_minutes` and `hidden_recipe_ids` remove recipes first.

**7. Deck assembly:** a deck holds at most 20 cards. That's up to 18 scored cards, followed by up to 2 all-staples cards, never more than 2 all-staples cards while scored recipes remain. Once the scored tier is used up, the remaining decks contain all-staples recipes only, up to 20 each. A deck that holds any scored card holds at most 2 all-staples cards, even when it is the last deck with scored cards: 30 scored and 10 all-staples recipes give decks of 18 + 2, 12 + 2, then 6.
For a deck smaller than 20, up to `size − 2` scored cards come first (never fewer than one while scored recipes remain), followed by up to 2 all-staples cards: a 10-card deck is 8 + 2, a 3-card deck 1 + 2, and a 1-card deck 1 + 0.

**8. What the card shows:** `match_percentage`, the share of core weight matched, rounded half-up to one decimal using integer arithmetic only: `tenths = (matched_q × 2000 + core_q) // (2 × core_q)`, then `match_percentage = tenths / 10`. No float is rounded at any point, so every server and client gets the same digits. It's shown alongside `matched_ingredients`, `missing_ingredients` and `assumed_staples` (each a list of `{id, name}`). All-staples cards show no percentage.

**9. The cursor is an opaque, signed, versioned token.** Clients treat it as a string and send it back unchanged.

- **Payload** (canonical JSON):
  - `v`: format version
  - `kid`: id of the key that signed it
  - `iat`: issued-at time, in Unix seconds
  - `catalog`: the catalog `content_hash` (ADR-0002 rule 7)
  - `scoring`: `SCORING_VERSION`, an integer constant in `recipe_app.domain.scoring`. It must be bumped whenever weights, the formula, tiers or the sort key change, and a test fails if the scoring constants change without it.
  - `req`: SHA-256 of the request's filters, `diet`, `max_total_minutes`, `excluded_staples` and `ingredient_ids`, with each list sorted, so that order doesn't matter. An omitted `diet` is hashed as `non_veg`, because both return the same recipes (ADR-0002 rule 6). `hidden_recipe_ids` is left out on purpose: the app adds a recipe to it on every left swipe, and hiding only removes cards, which never moves the position the cursor resumes from. Every deck leaves out the recipes hidden in its own request
  - `pos`: the sort key (rule 5) of the last card shown in each tier, `(-score_int, total_minutes, recipe_id)` or `(total_minutes, recipe_id)`, or null if the tier has shown nothing yet. The score is stored negated so that resuming is a single "greater than" comparison
- **Encoding:** `base64url(payload) + "." + base64url(HMAC-SHA256(key[kid], payload))`, without padding. Signatures are compared with `hmac.compare_digest`, which takes constant time.
- **Checks, cheapest first:** the length is at most 1,024 characters *before* any decoding. Then it must decode and split. Then `kid` must be a key we accept, the signature must be valid, `v` must be supported, `iat` must be no more than 24 hours old and no more than 5 minutes in the future (to allow for clock skew), and `req` must match this request. Finally, `catalog` and `scoring` must match what this pod is running.
- **Two outcomes, both `422`, with different problem `type`s** (RFC 9457):
  - `/problems/invalid-cursor`: the cursor is too long, malformed, has a bad signature, or `req` doesn't match. Only a client bug or tampering produces this. It's logged and counted.
  - `/problems/cursor-expired`: the cursor is older than 24 hours, `iat` is more than 5 minutes in the future (a pod's clock is off; the signature already proved we issued it), `catalog` or `scoring` differ, `v` is no longer supported, or `kid` isn't one we accept. This is a normal event, for example during a rolling deploy or after a catalog change. The app reacts by quietly requesting page 1 again, without showing an error.
- **Keys:** `CURSOR_SIGNING_KEYS` maps each `kid` to at least 32 random bytes, and `CURSOR_ACTIVE_KID` names the key used for signing. Both are injected at runtime from the secret store. They never appear in the repo, the image or the logs. Every listed key verifies cursors, and only the active one signs. The app refuses to start if the active key is missing or shorter than 32 bytes.
- **Rotation:** first add the new key as verify-only and deploy everywhere. Then make it active. After 24 hours, which is the maximum cursor age, remove the old key. For an emergency after a leak, remove the leaked key at once. Sessions holding its cursors get `cursor-expired` and restart from page 1, and nothing else breaks.

**10. Recipe times are whole minutes with fixed bounds.** A recipe stores `prep_minutes` and `cook_minutes`; `total_minutes` is always derived, never stored. Each is a whole number, 0 or more, so a raita (no cooking) and boiled eggs (no prep) are both valid. The total must be at least 1, because a recipe with nothing to prep or cook is food, not a recipe, and a zero total is usually a missing value. The total is at most 1,440 (24 hours, `MAX_TOTAL_MINUTES` in `recipe_app.domain.recipe`), which catches typos such as 3000 for 30. Prep and cook time count hands-on time only, so the card shows how long you are busy in the kitchen. Waiting that needs no hands, such as soaking, fermenting, marinating, resting or rising dough, chilling, setting and freezing, is not counted, and the steps say how long it takes. Short rests that are part of cooking, such as letting rice stand off the heat for 10 minutes, stay in cook time. Every seed author records idli, rajma or kulfi the same way. (Amended 30 Oct 2026: the owner chose to leave waiting time out of the total. Before this, soaking, fermenting and marinating counted as prep.) A recipe that breaks any of these is rejected when it is loaded, with the other seed-recipe checks in ADR-0002 rule 7.

## Consequences

- **Easier:** substantial dishes you can almost cook beat trivial ones, and a missing main ingredient costs more than a missing garnish.
- **Harder:** the shown percentage is weighted. A user missing 1 of 4 ingredients can see different percentages depending on which one. The ingredient lists on the card keep it honest.
- **Intended:** a small recipe missing one supporting ingredient (composite 0.298) ranks below a fully matched single-potato dish (0.301). With one item missing, a recipe needs core weight above about 2.0 (supporting missing), 2.9 (main missing) or 1.5 (unticked staple missing) to outrank it.
- **Accepted trade-off:** the weights and the log factor are hand-picked. Check them against saved and hidden swipes once there's data. Tuning them is a new ADR.
- **Accepted trade-off (rule 10):** recipes over 600 minutes, the largest `max_total_minutes` a search accepts, appear only in searches that send no time filter. A card shows the full total, so a 12-hour fermented dish looks long even though most of that time is waiting. Splitting active and waiting time is a later, additive field.
- **Harder:** every catalog change, `SCORING_VERSION` bump and removed key sends in-flight swipe sessions back to page 1 once. That's accepted, because a restart is visible and harmless, while silently computing page 2 under different rules duplicates or skips recipes. Tuning the weights (above) therefore always comes with a `SCORING_VERSION` bump.
- **Gate tests whose expected values change** from the original Task 1 file:
  - The potato recipe (potato, peas, tomato, onion, turmeric, salt, ghee) with `ingredient_ids: ["potato", "peas"]` scores **100%**, with tomato, onion, turmeric, salt and ghee listed as assumed. Unchanged.
  - The same recipe with `excluded_staples: ["turmeric"]` scores **85.7%** (1.5 / 1.75), with turmeric missing.
  - Kheer (rice A, milk B, sugar S) with `["rice"]` scores **66.7%** (1.0 / 1.5), not 50%, with milk missing.
  - Tomato soup (tomato, onion, garlic, butter, salt) lands in the all-staples tier for every user who hasn't unticked one of those staples. The old "typed tomato moves it out of the all-staples tier" test is retired.
  - Normalization tests become id tests (ADR-0001).
- **New tests this ADR requires:**
  - the potato trap: a curry with 3.5 of 4.0 core weight matched (0.572) outranks a fully matched single-potato dish (0.301)
  - a recipe whose core is empty for this request lands in the all-staples tier, with no exception
  - the rounding boundary: matching one supporting ingredient (2) of a 32-quarter core is exactly 6.25% and shows **6.3**. Python's `round(6.25, 1)` would give 6.2. The existing values stay 85.7 (6/7) and 66.7 (4/6).
  - the same request twice gives a byte-identical response
  - `score_int` is an integer, and the cursor round-trips it exactly
  - a tampered cursor, a cursor reused with different filters, and a 1,025-character cursor each return `/problems/invalid-cursor`. The long one is rejected before it is decoded.
  - a cursor still works when `hidden_recipe_ids` grows between decks, and when an omitted `diet` becomes `non_veg`; a recipe hidden after deck 1 is left out of deck 2
  - a cursor issued under a different catalog hash, a different `SCORING_VERSION`, or more than 24 hours ago returns `/problems/cursor-expired`
  - during a key rotation, a cursor signed with the old key is still accepted while that key is listed, and returns `cursor-expired` once it's removed
  - changing a weight constant without bumping `SCORING_VERSION` fails a test
