# ADR-0008: Recipes carry quantities, steps and a photo, written for this project

- Status: Accepted
- Date: 2026-10-29
- Amended: 2026-10-29 (rule 4: the step matcher also accepts regular plurals)
- Deciders: Nisha
- Amends: ADR-0001 rule 7 (quantities arrive in v1, not v2), ADR-0005 rule 2 (recipes are a directory of files)
- Related: ADR-0001 (append-only ids), ADR-0002 rule 7 (data reviewed in pull requests), ADR-0005 (Postgres, the sync), ADR-0006 (web app, content security policy)

## Context

The 47 recipes in `data/recipes.v1.toml` are a name, prep and cook minutes, and a list of catalog ingredient ids. There are no quantities and no method, so a user who swipes right on a recipe still can't cook it. The recipe screen shows a drawn bowl, the same for every dish. The ingredient lists were written to exercise the matcher and were never checked against a real version of each dish.

The target is about 1,000 recipes (600 Indian across regions, 400 international), each with quantities, numbered steps and a photo plated like a restaurant dish. They are expected to stay fixed once written; new recipes are added over time.

Where the content comes from was weighed first:

- **Written for this project (chosen).** No licence question on the text, every recipe uses our catalog ids from the start, and one consistent voice and format. Nobody has cooked from them, so each batch is spot-read before merge, and the automated checks in rule 4 catch the mistakes a reader would miss across 1,000 recipes.
- **Wikibooks Cookbook (CC BY-SA).** Uneven quality and format, a credit line per recipe, edits stay under CC BY-SA, and each recipe still needs mapping to catalog ids by hand.
- **TheMealDB.** About 30 Indian dishes, and the free key is meant for development, not a released app.
- **Scraped datasets (RecipeNLG, Food.com).** The method text belongs to the sites it was scraped from; RecipeNLG is licensed for non-commercial research only.

Ingredient lists are facts. The method text and photos are creative work, which is why the source matters for them.

## Decision

**1. Recipe text is written for this project.** No step is copied or paraphrased line by line from a book, site or dataset. Recipes are written in batches of about 300 (about 100 for the first three), one pull request per batch. Nisha read a sample of each of the first four batches before merging; from batch 5 on, the independent review and the automated checks stand in for that read.

**2. Each recipe gains servings, quantities and steps.**

```toml
[[recipe]]
id = "01a15175-3c02-76b4-b315-57189e41c2d0"
name = "Aloo gobi"
serves = 4
prep_minutes = 15
cook_minutes = 25
ingredients = [
  { id = "potato", amount = 3, unit = "medium" },
  { id = "cauliflower", amount = 1, unit = "small-head" },
  { id = "turmeric", amount = 0.5, unit = "tsp" },
  { id = "oil", amount = 2, unit = "tbsp" },
  { id = "salt", to_taste = true },
]
steps = [
  "Cut the potatoes into 2 cm cubes and the cauliflower into small florets.",
  "Heat the oil in a wide pan over medium heat ...",
]
image = { file = "01a15175-3c02-76b4-b315-57189e41c2d0.webp", sha256 = "9f2c…", alt = "Aloo gobi with coriander, in a copper bowl" }
```

- `serves` is a whole number from 1 to 12: the servings the amounts are written for.
- Each ingredient has either an `amount` and a `unit`, or `to_taste = true` (salt, sugar to adjust, oil for frying). `amount` is a number above 0, written as a decimal (`0.5`, `0.25`, `0.333` for a third). `unit` comes from one fixed list in the domain, so the app can scale and display it (rule 8):

  | Kind | Units (plural forms) | Grid: written and shown amounts |
  |---|---|---|
  | mass | `g`, `kg` | g: multiples of 5 under 100, of 10 from 100; kg: multiples of 0.05 |
  | volume | `ml`, `l` | ml: multiples of 5 under 100, of 10 from 100; l: multiples of 0.05 |
  | spoons and cups | `tsp`, `tbsp`, `cup` (`cups`) | quarters and thirds (¼, ⅓, ½, ⅔, ¾ and whole numbers with them) |
  | produce by size | `small`, `medium`, `large`, `small-head` (`small-heads`), `bunch` (`bunches`) | halves |
  | countable | `piece` (`pieces`), `clove` (`cloves`), `sprig` (`sprigs`), `slice` (`slices`), `leaf` (`leaves`), `pinch` (`pinches`), `can` (`cans`) | whole numbers |

  - **Written amounts sit on the grid.** Rule 4 checks that every written amount equals its own displayed value, so the screen at the written servings shows exactly what the file says. Half a `piece` or `can` is not allowed; a half belongs to the produce units, or the recipe uses grams.
  - **Scaled amounts round to the nearest grid value, never below one grid step**: ¼ tsp, 5 g, 5 ml, ½ medium, 1 clove. The floor is intentional: 1 clove at serves 4 stays 1 clove at serves 1, because a recipe never needs none of an ingredient it lists.
  - **The display keeps the written unit, with one switch each way for metric:** 1,000 g or more shows in kg and 1,000 ml or more in l (600 g × 3 shows "1.8 kg", 250 ml × 6 shows "1.5 l"). Spoons, cups and countable units never convert.
  - The domain table holds each unit's singular and plural forms; the screen shows the plural for amounts above 1.

  Adding a unit is a domain change with its forms and grid, never a free-text value. There is no `inch`: ginger and similar are weighed in `g`, so "1 inch" is never an amount. How an ingredient is cut or cooked belongs in the steps, not the unit.
- `steps` is 2 to 20 plain sentences of at most 400 characters each, in cooking order. The file does not number them; the screen does. Steps never repeat an ingredient's amount ("add the water", not "add 2 cups of water"), because the steps don't scale. Times, temperatures and sizes are fine ("10 minutes", "180 °C", "2 cm cubes"); sizes are written in cm only.
- `image` is optional. Its `file` is the recipe id plus `.webp`, `sha256` is the file's SHA-256 in hex (rule 6), and `alt` describes the plated dish for screen readers. A third-party photo would also need a `credit` and `licence`; none is planned (rule 6).

Ingredient order, ids and the rules of ADR-0002 rule 6 are unchanged. The 47 existing recipes are converted in the same pull request as the loader.

**3. Recipes live in several files.** One file of 1,000 recipes with steps is a few megabytes and unreviewable in a diff. Recipes move to `data/recipes/*.toml`, one file per group in the dish list (for example `north-indian-curries.toml`). The loader reads every file in name order, and ids and normalized names stay unique across all of them. Recipe ids stay published and append-only (ADR-0001 rule 2).

**4. CI checks every recipe's content.** On top of the existing recipe checks:

- every field in rule 2 is present and in range, and every unit is on the list;
- every written amount is on its unit's grid (rule 2);
- no step states an amount: a number followed by any singular or plural form of a unit on the list, with or without "of" between them, is rejected. A number is digits or decimals (`2`, `1.5`), a slash fraction (`1/2`), a Unicode fraction alone or after digits (`½`, `1½`), the words one to twelve, "half", or, before a mass, volume, spoon, cup or countable unit only, "a" or "an" ("a cup of water", "a pinch of salt"). "A" before a produce size is left alone, because "a large pan" and "a medium heat" are not amounts;
- every non-staple ingredient in the list is named in at least one step, by its name or one of its catalog search terms, so a step never forgets an ingredient;
- no step names a catalog ingredient, by name or search term, that is not in the recipe's list, so the list never forgets one the steps use;
- every `image.file` exists under `web/public/dishes/` with the `sha256` the recipe records, and every file there belongs to a recipe.

The two ingredient checks share one matcher. It normalizes each step as the search does (ADR-0001) and scans it once, left to right. At each position it takes the longest catalog phrase (any ingredient's name or search term) that matches whole words there, records that ingredient, and continues after the phrase, so matches never overlap. Each phrase also matches with its last word in the regular English plural (+s, +es, or y to ies), unless that form is already another ingredient's phrase, so "boil the potatoes" finds `potato` without a search term for every plural. Retired ingredients are not phrases. Only the ingredients found that way count for both checks. "Pour in the coconut milk" therefore finds `coconut-milk` and neither `coconut` nor `milk`, and "oil" never matches inside "boil". The loader's tests cover at least "coconut milk", "coconut oil" and "green chillies". A false match that remains is fixed by rewording the step, never by an allow-list.

**5. The database and the sync carry the new fields.** One migration adds `recipes.serves`, `recipes.image_file` and `recipes.image_alt`, `recipe_ingredients.amount` (numeric, NULL for to-taste) and `recipe_ingredients.unit` (text with a `CHECK` on the list, NULL together with `amount`), `recipes.image_sha256`, and a new `recipe_steps` table (recipe, position, text; primary key recipe and position). The sync writes them on every run like the rest of a recipe. This amends ADR-0005 rule 2: the sync parses the catalog file and every file in `data/recipes/`, with the same checks and the same single transaction. The search queries and their indexes do not read any of them, so the ADR-0007 latency budget is unaffected.

**6. Photos are generated, stored with the web app, and served from our own origin.** Nisha generates each photo in her image tool from a prompt written per dish, with one shared style block so every photo looks like the same restaurant. Each is saved as an 800 × 800 WebP of at most 150 KB in `web/public/dishes/`, named by recipe id. This ADR fixes `img-src 'self'` for the page's content security policy, which issue #41 adds alongside the `connect-src 'self'` that ADR-0006 rule 3 sets. Serving photos from our own origin is what lets the policy stay that strict, and no third party sees which recipes a user opens. A regenerated photo keeps its file name, so the API URL carries a version taken from the file's hash, `/dishes/<file>?v=<first 12 hex of sha256>`. Browsers and any CDN can then cache `/dishes/` for a year, and a new photo is a new URL. The hash is in the data file, so the sync needs no access to the web files, and rule 4 checks it matches the file. A photo is a generated likeness of the dish, not a photograph of a real one; one that looks wrong is regenerated.

**7. The API adds the fields to the recipe detail only.** `GET /api/v1/recipes/{id}` gains `serves`, `ingredients[].amount` and `ingredients[].unit` (both `null` for to-taste ingredients), `steps` (a list of strings) and `image` (`{ "url", "alt" }` or `null`). The URL is a path on the web origin, `/dishes/<file>?v=<version>` (rule 6). Search cards do not change, so a deck stays small. The change only adds fields, so it stays in `/api/v1`. This amends ADR-0001 rule 7, which expected quantities in v2: its id-and-name objects are what let them arrive in v1 as added fields without breaking a client.

**8. The recipe screen shows the photo, quantities and method.** Order: the photo (the drawn bowl when a recipe has none), the name and times, a servings stepper (1 to 12, starting at the recipe's `serves`), the three ingredient groups with each amount, then a numbered "Method" section. Changing the servings multiplies every amount by new servings ÷ `serves` in the app and shows it with the rounding in rule 2; to-taste ingredients say "to taste" at any size. The server always returns the written amounts, so the API stays cacheable and the scaling has one implementation, in the app, with its own unit tests. The chosen servings are not saved; each recipe opens at its written size.

## Consequences

- **Easier:** a saved recipe can be cooked from the app, for any number of people up to 12. New recipes are a data pull request, checked by CI and synced, with no code change.
- **Harder:** about 1,000 recipes is a lot to read. The checks in rule 4 catch structural mistakes; only a cook catches a wrong ratio or time, so the batch spot-read matters.
- **Risk:** 1,000 photos at up to 150 KB is up to 150 MB in the Git history, and history never shrinks. Before the photos pass 100, a follow-up ADR decides between Git LFS and object storage behind the same `/dishes/` path. ADR-0011 decided to keep them in Git.
- **Risk:** scaling is linear. Spices, salt and cooking times don't scale linearly, so at 3× a recipe can taste stronger than intended. The stepper stops at 12 and to-taste stays to-taste; anything smarter is v2.
- **Deferred:** step photos, unit conversion (cups to grams), and nutrition.
