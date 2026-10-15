ADR-0003: Recipes are ranked by a weighted, size-aware score with a deterministic integer sort key
Status: Accepted
Date: 2026-10-15
Deciders: Nisha
Supersedes: the "Result shape" ranking rule, the plain match-percentage definition, and the "fresh staple typed is promoted to core" rule in the Task 1 "Product decisions locked" table
Related: ADR-0001, ADR-0002
Context

The original v1 rule ranked by plain match % over core ingredients: matched ÷ core. That rule has a "potato trap". A one-ingredient dish you can cook scores 100% and sits above a nearly complete ten-ingredient curry. It also treats a missing chilli the same as a missing kilo of paneer. Ingredients matter unequally, and users prefer complete, substantial dishes. Whatever replaces the rule must stay deterministic for cursor pagination, must never divide by zero, and must stay explainable on the card.

Decision

1. Weights come from the ingredient class (ADR-0002): A = 1.0, B = 0.5, an unticked staple = 0.25, a ticked staple = not counted. The constants live in one domain module.

2. For each candidate recipe r and this request:

core(r) = every class A and B ingredient of r, plus every staple of r that is in excluded_staples (at W = 0.25).
assumed(r) = every other staple of r, returned as assumed_staples.
matched(r) = core(r) ∩ ingredient_ids. missing(r) = core(r) − ingredient_ids.

Excluded staples are never in ingredient_ids (ADR-0001 rejects staple ids there), so an excluded staple in a recipe is always missing.

3. Two tiers:

Scored tier: matched(r) is not empty. At least one ticked ingredient appears in the recipe.
All-staples tier: core(r) is empty for this request: the recipe uses only staples, and none of them are excluded. These recipes get no score, so no division happens.
A recipe with a non-empty core and no matches is not shown.

4. The score, for the scored tier only:

match_ratio = Σ W(matched) / Σ W(core)                  # 0 < match_ratio ≤ 1, denominator > 0
composite   = match_ratio × log10(Σ W(matched) + 1)
score_int   = round(composite × 1_000_000)               # the only value used for sorting

score_int is computed in exactly one pure function in recipe_app.domain.scoring. The database selects candidates but never computes or sorts by the score.

5. The sort key is a total order:

Scored tier: (-score_int, total_minutes, recipe_id), where total_minutes = prep_minutes + cook_minutes.
All-staples tier: (total_minutes, recipe_id).

6. Filters run before ranking and deck assembly: diet, max_total_minutes and hidden_recipe_ids remove recipes first.

7. Deck assembly: a deck holds at most 20 cards. That's up to 18 scored cards, followed by up to 2 all-staples cards, never more than 2 all-staples cards while scored recipes remain. Once the scored tier is used up, the remaining decks contain all-staples recipes only, up to 20 each.

8. What the card shows: match_percentage = match_ratio × 100, rounded to one decimal, alongside matched_ingredients, missing_ingredients and assumed_staples (each a list of {id, name}). All-staples cards show no percentage.

9. The cursor encodes the last position in each tier, a hash of diet, max_total_minutes, hidden_recipe_ids, excluded_staples and ingredient_ids, and a format version. It's base64-encoded and HMAC-signed. A tampered cursor, or one reused with a different request, returns 422.

Consequences
Easier: substantial dishes you can almost cook beat trivial ones, and a missing main ingredient costs more than a missing garnish.
Harder: the shown percentage is weighted. A user missing 1 of 4 ingredients can see different percentages depending on which one. The ingredient lists on the card keep it honest.
Intended: a small recipe missing one supporting ingredient (composite 0.298) ranks below a fully matched single-potato dish (0.301). With one item missing, a recipe needs core weight above about 2.0 (supporting missing), 2.9 (main missing) or 1.5 (unticked staple missing) to outrank it.
Accepted trade-off: the weights and the log factor are hand-picked. Check them against saved and hidden swipes once there's data. Tuning them is a new ADR.
Gate tests whose expected values change from the original Task 1 file:
The potato recipe (potato, peas, tomato, onion, turmeric, salt, ghee) with ingredient_ids: ["potato", "peas"] scores 100%, with tomato, onion, turmeric, salt and ghee listed as assumed. Unchanged.
The same recipe with excluded_staples: ["turmeric"] scores 85.7% (1.5 / 1.75), with turmeric missing.
Kheer (rice A, milk B, sugar S) with ["rice"] scores 66.7% (1.0 / 1.5), not 50%, with milk missing.
Tomato soup (tomato, onion, garlic, butter, salt) lands in the all-staples tier for every user who hasn't unticked one of those staples. The old "typed tomato moves it out of the all-staples tier" test is retired.
Normalization tests become id tests (ADR-0001).
New tests this ADR requires:
the potato trap: a curry with 3.5 of 4.0 core weight matched (0.572) outranks a fully matched single-potato dish (0.301)
a recipe whose core is empty for this request lands in the all-staples tier, with no exception
the same request twice gives a byte-identical response
score_int is an integer, and the cursor round-trips it exactly