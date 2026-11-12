# ADR-0012: Recipe search, food rules, the mood screen and pairings

- Status: Proposed
- Date: 2026-11-12
- Deciders: Nisha
- Amends: ADR-0002 rule 6 (Jain sits beside the diet order, not in it), ADR-0003 rules 5, 6 and 9 (new filters, mood and weather fit first in the sort key, more fields in the cursor's `req`), ADR-0006 rule 5 (the device store gains food rules and mood picks), ADR-0008 rule 7 (the recipe detail and the search cards gain fields)
- Related: ADR-0007 (Postgres ranks), ADR-0009 (plan-ahead label), the approved mockups (12 Nov 2026)

## Context

Today the app has one way in: tick what is in your pantry, then swipe a deck ranked by how much of each recipe you have. Its filter sheet offers four diets and a time limit. Nisha asked for four more things, agreed in a brainstorm and approved as mockups on 12 Nov 2026:

1. **Search** for any recipe by name, with a dropdown of matches as you type.
2. **Food rules** set once and remembered: a diet, now including Jain, and allergies. A recipe that breaks them never appears in the deck.
3. **A short mood screen** before the deck: what you are making, how long you have, and, under "Fine-tune", what you are in the mood for and how the weather is making you feel. Every part is optional, and skipping it all deals today's deck.
4. **"Pairs well with"** at the bottom of a recipe, such as phulka, butter naan, jeera rice and cucumber raita under paneer butter masala.

None of this can be computed from what a recipe knows today (name, servings, times, ingredients, steps, photo, plan-ahead). A recipe has no cuisine, course, flavour or weather, and an ingredient has no allergens. The data has to be written, like the recipes were (ADR-0008 rule 1).

## Decision

**1. Recipes gain six fields, all from fixed lists.** In a recipe file:

```toml
cuisine = "north-indian"
courses = ["mains"]
moods = ["creamy", "comforting", "savoury"]
weather = ["cosy-night-in", "want-something-warming"]
also_known_as = ["paneer makhani"]
pairs_with = ["01a188ac-05a7-7dde-b069-03b15b2dd2b3", "01a15175-3c10-76ca-bf43-23fffb096acd"]
```

- `cuisine`: exactly one id from the cuisine list in `recipe_app.domain.tags` (north-indian, south-indian, east-indian, west-indian, indo-chinese, street-food, chinese, japanese, korean, thai, southeast-asian, middle-eastern, mediterranean, italian, french, spanish-portuguese, european, american-british, mexican-latin, african-caribbean). It labels the search dropdown and lets "Thai" find Thai dishes.
- `courses`: 1 or 2 of `breakfast`, `snacks-starters`, `soups`, `salads`, `mains`, `rice-breads`, `sides`, `desserts`, `drinks`.
- `moods`: 1 to 3 of `spicy`, `tangy`, `sweet`, `savoury`, `creamy`, `smoky`, `fresh-herby`, `comforting`, `crispy`, `sweet-sour`, `light`, `hearty`. A tag means the flavour is what the dish is known for, not that it is present at all.
- `weather`: 0 to 3 of `cool-down`, `rainy-day-cosy`, `warming`, `just-pleasant`, `grey-gloomy`, `cosy-night-in`, `sticky-sluggish`, `breezy-evening`, `under-the-weather`. Most everyday dishes suit any weather and have none.
- `also_known_as`: 0 to 5 other names people type, such as "aloo" names, Hindi names for English dishes and common spellings ("biriyani"). 1 to 60 characters each, lower case.
- `pairs_with`: 0 to 4 recipe ids, each an existing, different recipe, hand-picked (rule 8).

Lists hold no duplicates. The ids are published like ingredient ids: never renamed or reused (ADR-0001 rule 2). The web app owns the labels ("Fresh and herby", "Rainy-day cosy").

**2. Ingredients gain allergens and a Jain flag.** In `data/ingredients.v1.toml`:

- `allergens`: 0 or more of the 14 allergens food labels use: `peanuts`, `tree-nuts`, `dairy`, `egg`, `gluten`, `soy`, `sesame`, `fish`, `crustaceans`, `molluscs`, `mustard`, `celery`, `sulphites`, `lupin`. Ready-made ingredients carry what they usually contain: soy sauce is `soy` and `gluten`, fish sauce `fish`, Worcestershire sauce `fish`, `gluten` (malt vinegar) and `sulphites`, Thai curry paste `crustaceans` (shrimp paste), wine `sulphites`, ready-made pickles (achaar) and kasundi `mustard`. Compounded asafoetida (hing) is cut with wheat flour, so it is `gluten`. When the usual recipe varies, the tag errs towards listing it.
- Oils and seeds carry their source: mustard oil and mustard seeds are `mustard`, sesame oil and sesame seeds `sesame`, peanut (groundnut) oil `peanuts`. Refined or cold-pressed does not change the tag. Plain "oil" means a neutral vegetable oil and has none.
- `jain = false` on every vegan or vegetarian ingredient a Jain kitchen leaves out: onion, garlic, potato and other roots and tubers (carrot, beetroot, radish, sweet potato, yam, fresh ginger and fresh turmeric), mushrooms and honey. It is absent, meaning true, on everything else. Egg and non-veg ingredients need no flag, because the diet already excludes them.

A recipe's allergens are the union of its ingredients' allergens. A recipe is Jain when its diet is vegan or vegetarian and none of its ingredients has `jain = false`. Both are computed, never hand-labelled, like diet (ADR-0002 rule 6). Jain cannot join the diet order: a vegan dish with onion is not Jain, and a Jain dish with paneer is not vegan.

**3. The loader and CI check every new field.** On load, every recipe has a cuisine, 1 or 2 courses and 1 to 3 moods; every tag is on its list; `pairs_with` ids exist and are not the recipe itself; aliases are unique within a recipe and are not the recipe's own name. Every allergen is on the list. A bad file stops the app from starting, as today.

**4. Food rules are filters, and they apply to the deck only.** The deck request, `POST /api/v1/recipes/search`, gains:

- `jain`: `false` by default. `true` deals only Jain recipes and requires `diet` to be `vegetarian` or `vegan` (else `422`). The app's "Jain" diet choice sends `diet = vegetarian` and `jain = true`.
- `avoid_allergens`: up to 14 allergen ids. A recipe with any of them never appears in the deck.
- `avoid_ingredient_ids`: up to 50 ingredient ids, for the "Something else? Search any ingredient" part of food rules (coconut, mushroom). A recipe with any of them never appears.

They run first, with `diet`, the time filters and `hidden_recipe_ids` (ADR-0003 rule 6). **Recipe search (`GET /api/v1/recipes?q=`, rule 10) and the recipe detail (`GET /api/v1/recipes/{id}`) ignore the food rules and return every recipe** (Nisha, 12 Nov). They return each recipe's allergens and Jain flag, so the dropdown and the recipe screen show what a recipe contains, and the app compares it with the rules on the device: a red tag in the dropdown ("Contains peanuts") and a note at the top of the recipe ("Contains tree nuts: this recipe uses cashews, and your food rules say you're allergic to tree nuts. It won't appear in your deck."). "Pairs well with" hides pairings that break the rules.

Allergens are best-effort. The food rules screen and every allergy note say that ready-made items can hide allergens and to check their labels.

**5. The mood screen adds filters and one nudge.** The deck request gains:

- `courses`: up to 9 course ids. A recipe must have at least one of them.
- `moods`: up to 12 mood ids. A recipe must have at least one of them ("any of", so Spicy plus Tangy deals dishes that are either).
- `weather`: up to 9 weather ids. **This never removes a recipe**; it only moves recipes that suit any of them forward (rule 6).
- `min_total_minutes`: with `max_total_minutes`, the time choice. The app sends Any (neither), 15 min (`max 15`), 30 min (`max 30`), 1 hr (`max 60`) or 1 hr+ (`min 61`). The 45-minute choice goes. The time limit moves from the deck's filter sheet to the mood screen, so it lives in one place.

**6. The sort key puts fit first.** For each recipe, `fit` = the number of requested moods it has, plus 1 if it suits any requested weather. With nothing picked, every `fit` is 0. The scored tier sorts by `(-fit, -score_int, total_minutes, recipe_id)`, so a recipe that fits more of the picked moods and weather comes before one that fits fewer, and pantry match orders recipes with the same fit. With nothing picked, the order is exactly today's. The all-staples tier sorts by `(-fit, total_minutes, recipe_id)`. `SCORING_VERSION` is bumped, and the cursor's `pos` stores the new keys. Postgres computes `fit` by counting array overlaps and still only looks up `score_int` (ADR-0007 rule 2 holds: SQL never evaluates the score formula).

Nisha chose this order on 12 Nov over "pantry first, fit breaks ties": what you picked on the mood screen leads, and pantry match comes second. A consequence: with Spicy and Tangy picked, a dish that is both and needs a bigger shop comes before a dish that is only spicy and uses everything you have. The deck's tier rule still holds, so a recipe with nothing matched never appears (ADR-0003 rule 3).

**7. The cursor covers every new field.** `req` hashes `jain`, `avoid_allergens`, `avoid_ingredient_ids`, `courses`, `moods`, `weather` and `min_total_minutes` alongside today's fields, each list sorted (ADR-0003 rule 9).

**8. Pairings are hand-picked and shipped in the recipe detail.** Rules such as "a curry gets a bread" pick odd matches (naan with a Thai curry), so pairings are written per recipe, like the steps. Mains, soups and starters get 2 to 4 where there is something natural to serve alongside. `GET /api/v1/recipes/{id}` gains `pairs_with`: a list of small cards (`id`, `name`, `image`, `total_minutes`, `courses`, `diet`, `jain`, `allergens`) in the order written. The app filters them by the food rules, so the endpoint stays one cacheable response per recipe.

**9. Responses carry what the screens need.**

- Search cards gain `cuisine`, `courses`, `moods`, `weather_fit` (true when the recipe suits a requested weather, for the "Rainy-day pick" badge), `jain` and `allergens`.
- The recipe detail gains the same plus `pairs_with` (rule 8), and `allergens` there lists which ingredient brings each one: `[{ "allergen": "tree-nuts", "ingredients": [{ "id": "cashews", "name": "Cashews" }] }]`.

Adding fields keeps both responses in `/api/v1`.

**10. Recipe search has its own endpoint.** `GET /api/v1/recipes?q=pa&limit=8` returns up to `limit` (1 to 20, default 8) recipes. `q` is 2 to 60 characters; it is lower-cased and Unicode-normalised like ingredient search (ADR-0001). It matches, best first:

1. the start of the recipe name ("pa" finds Paneer butter masala, Pad thai);
2. the start of any word in the name or in `also_known_as`;
3. a close spelling of the name or an alias, using Postgres `pg_trgm` similarity of at least 0.3 ("biriyani" finds Biryani);
4. a recipe that uses an ingredient whose name or search terms start with `q` ("paneer"), or whose cuisine label does ("thai").

A recipe that matches more than one way takes its best. Results sort by that criterion first (1 before 2 before 3 before 4), then within criterion 3 by similarity, highest first, then by name. So "chicken" lists dishes named "Chicken …" before dishes that only use chicken, and the dropdown is never just the alphabetically first matches. Each result has `id`, `name`, `cuisine`, `total_minutes`, `diet`, `jain`, `image`, `allergens` and `ingredient_ids`, so the app shows "You have 9 of 13" from the pantry on the device without sending it. The response sets `Cache-Control: public, max-age=300`. The sync stores one lower-cased search text per recipe (name, aliases) with a trigram GIN index. The index needs `CREATE EXTENSION IF NOT EXISTS pg_trgm`, which ships as its own migration ahead of the index, deployed as a separate step like every migration (ADR-0005). The role that runs migrations must be allowed to create extensions; `pg_trgm` is a trusted extension since Postgres 13, so a database owner can create it on managed Postgres without superuser. Budget on the 50,000-recipe gate seed: p95 at most 100 ms, checked by the CI latency job like the deck search (ADR-0007 rule 7).

The dropdown also shows matching ingredients ("tap to add to pantry") from the catalog the app already holds, so the pantry's search box becomes one box for both. Other screens (deck, cookbook) get a search button that opens the same box.

**11. "See all" opens a results list, not a deck.** The approved mockup's button read "See all 41 recipes as a deck". A deck is ranked by pantry match, and a search for "pa" with an empty pantry would deal almost nothing, because a recipe with nothing matched is in neither tier (ADR-0003 rule 3). The button reads "See all 41 recipes" and opens a scrolling list of the same results, 20 at a time (`offset` on the same endpoint, up to 200). Each row opens the recipe, where it can be saved.

**12. The device store gains a version.** ADR-0006 rule 5 holds: v1 has no accounts and the device keeps the only copy. The store adds `foodRulesSeen`, `jain`, `avoidAllergens`, `avoidIngredients` and `mood` (`courses`, `time`, `moods`, `weather`), with a version bump and a migration. `maxTotalMinutes` becomes the `time` choice: 15 and 30 keep their value, 45 and 60 become "1 hr". The food rules screen opens once on first launch (with "Skip for now") and again from a profile button on the pantry. The mood screen opens from "Cook something", remembers the last picks and shows them on the deck as one chip ("Snacks · 30 min · Spicy, Tangy · Rainy-day cosy") that opens it again.

**13. A deck that runs short says so.** When moods or courses leave fewer than 5 cards on the first deck, the deck ends with "Only 3 recipes match. Show more?", which deals again without moods, and then without courses. Food rules are never widened.

**14. Delivery order.** One pull request each, reviewed and squash-merged in order:

1. This ADR.
2. Data model: the domain lists, loader checks, a migration, the sync and the API fields, with every new field optional and no recipe using it yet (as ADR-0009 rule 5 did).
3. Content: allergens and Jain flags on all ingredients, then cuisine, courses, moods, weather and aliases on all 1,000 recipes, then pairings, in pull requests of about 200 recipes. Then a pull request makes cuisine, courses and moods required.
4. API: the new filters, the sort key, recipe search and the latency budget.
5. Web: food rules, search, the mood screen, the deck chip and the recipe screen.

## Consequences

- **Easier:** a cook finds a dish by name, never sees what they are allergic to or don't eat, and narrows the deck to what they feel like in two taps without filling in a form.
- **Harder:** every new recipe needs six more fields written, and allergen tags must be kept true as ingredients are added. Allergen data is a safety feature written by hand, so a wrong tag can show someone a dish they react to. The disclaimer and the conservative tagging of ready-made items reduce this; they do not remove it.
- **Deferred:** learning from swipes, a cuisine picker, festival and occasion picks, and replacing grams with kitchen measures for ingredients not bought by weight (Nisha, 12 Nov).
