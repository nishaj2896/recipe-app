# ADR-0008: Recipes carry quantities, steps and a photo, written for this project

- Status: Proposed
- Date: 2026-10-29
- Deciders: Nisha
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

**1. Recipe text is written for this project.** No step is copied or paraphrased line by line from a book, site or dataset. Recipes are written in batches of about 100, one pull request per batch, and Nisha reads a sample of each batch before merging.

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
image = { file = "01a15175-3c02-76b4-b315-57189e41c2d0.webp", alt = "Aloo gobi with coriander, in a copper bowl" }
```

- `serves` is a whole number from 1 to 12: the servings the amounts are written for.
- Each ingredient has either an `amount` and a `unit`, or `to_taste = true` (salt, sugar to adjust, oil for frying). `amount` is a number above 0, written as a decimal (`0.5`, `0.25`, `0.333` for a third). `unit` comes from one fixed list in the domain, so the app can scale and display it (rule 8):

  | Kind | Units | Shown rounded to |
  |---|---|---|
  | mass | `g`, `kg` | 5 g under 100 g, then 10 g; kg to 0.05 |
  | volume | `ml`, `l` | 5 ml under 100 ml, then 10 ml; l to 0.05 |
  | spoons and cups | `tsp`, `tbsp`, `cup` | quarters, plus thirds (¼, ⅓, ½, ⅔, ¾) |
  | produce by size | `small`, `medium`, `large`, `small-head`, `bunch` | halves |
  | countable | `piece`, `clove`, `sprig`, `slice`, `leaf`, `pinch`, `inch`, `can` | whole numbers, at least 1 |

  Adding a unit is a domain change with its rounding, never a free-text value. How an ingredient is cut or cooked belongs in the steps, not the unit.
- `steps` is 2 to 20 plain sentences of at most 400 characters each, in cooking order. The file does not number them; the screen does. Steps never repeat an ingredient's amount ("add the water", not "add 2 cups of water"), because the steps don't scale. Times, temperatures and sizes ("10 minutes", "180 °C", "2 cm cubes") are fine.
- `image` is optional. Its `file` is the recipe id plus `.webp`, and `alt` describes the plated dish for screen readers. A third-party photo would also need a `credit` and `licence`; none is planned (rule 6).

Ingredient order, ids and the rules of ADR-0002 rule 6 are unchanged. The 47 existing recipes are converted in the same pull request as the loader.

**3. Recipes live in several files.** One file of 1,000 recipes with steps is a few megabytes and unreviewable in a diff. Recipes move to `data/recipes/*.toml`, one file per group in the dish list (for example `north-indian-curries.toml`). The loader reads every file in name order, and ids and normalized names stay unique across all of them. Recipe ids stay published and append-only (ADR-0001 rule 2).

**4. CI checks every recipe's content.** On top of the existing recipe checks:

- every field in rule 2 is present and in range, and every unit is on the list;
- no step contains a number followed by a unit from the list, so a step never states an amount that would go stale when the servings change;
- every non-staple ingredient in the list is named in at least one step, by its name or one of its catalog search terms, so a step never forgets an ingredient;
- no step names a catalog ingredient, by name or search term, that is not in the recipe's list, so the list never forgets one the steps use;
- every `image.file` exists under `web/public/dishes/`, and every file there belongs to a recipe.

The two step checks match whole words after the same normalization as the search (ADR-0001), so "oil" does not match "boil". A false match is fixed by rewording the step, never by an allow-list.

**5. The database and the sync carry the new fields.** One migration adds `recipes.serves`, `recipes.image_file` and `recipes.image_alt`, `recipe_ingredients.amount` (numeric, NULL for to-taste) and `recipe_ingredients.unit` (text with a `CHECK` on the list, NULL together with `amount`), and a new `recipe_steps` table (recipe, position, text; primary key recipe and position). The sync writes them on every run like the rest of a recipe (ADR-0005 rule 2). The search queries and their indexes do not read any of them, so the ADR-0007 latency budget is unaffected.

**6. Photos are generated, stored with the web app, and served from our own origin.** Nisha generates each photo in her image tool from a prompt written per dish, with one shared style block so every photo looks like the same restaurant. Each is saved as an 800 × 800 WebP of at most 150 KB in `web/public/dishes/`, named by recipe id. Serving them from the app's own origin keeps the content security policy at `img-src 'self'` (ADR-0006) and means no third party sees which recipes a user opens. A photo is a generated likeness of the dish, not a photograph of a real one; one that looks wrong is regenerated.

**7. The API adds the fields to the recipe detail only.** `GET /api/v1/recipes/{id}` gains `serves`, `ingredients[].amount` and `ingredients[].unit` (both `null` for to-taste ingredients), `steps` (a list of strings) and `image` (`{ "url", "alt" }` or `null`). The URL is a path on the web origin, `/dishes/<file>`. Search cards do not change, so a deck stays small. The change only adds fields, so it stays in `/api/v1`.

**8. The recipe screen shows the photo, quantities and method.** Order: the photo (the drawn bowl when a recipe has none), the name and times, a servings stepper (1 to 12, starting at the recipe's `serves`), the three ingredient groups with each amount, then a numbered "Method" section. Changing the servings multiplies every amount by new servings ÷ `serves` in the app and shows it with the rounding in rule 2; to-taste ingredients say "to taste" at any size. The server always returns the written amounts, so the API stays cacheable and the scaling has one implementation, in the app, with its own unit tests. The chosen servings are not saved; each recipe opens at its written size.

## Consequences

- **Easier:** a saved recipe can be cooked from the app, for any number of people up to 12. New recipes are a data pull request, checked by CI and synced, with no code change.
- **Harder:** about 1,000 recipes is a lot to read. The checks in rule 4 catch structural mistakes; only a cook catches a wrong ratio or time, so the batch spot-read matters.
- **Risk:** 1,000 photos at up to 150 KB is up to 150 MB in the Git history, and history never shrinks. Before the photos pass 100, a follow-up ADR decides between Git LFS and object storage behind the same `/dishes/` path.
- **Risk:** scaling is linear. Spices, salt and cooking times don't scale linearly, so at 3× a recipe can taste stronger than intended. The stepper stops at 12 and to-taste stays to-taste; anything smarter is v2.
- **Deferred:** step photos, unit conversion (cups to grams), and nutrition.
