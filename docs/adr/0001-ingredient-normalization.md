# ADR-0001: Users pick ingredients from a catalog by id; normalization applies only to catalog data and search

- Status: Accepted
- Date: 2026-10-15
- Deciders: Nisha

## Context

Free-text ingredient entry forces the server to turn `"Tomatoes "`, `"TOMATO"` and `"tomato"` into one canonical ingredient. It needs alias tables, plural rules, handling for unknown words and typos, and every one of those is a source of silent mismatches. Yet recipes can only ever use ingredients in our catalog, so an ingredient the catalog doesn't know can never match anything anyway. A picker that only offers catalog ingredients removes that whole class of problems from the request path. Normalization is still needed in two places: when the catalog is loaded (so it has no near-duplicate names), and when a user searches the picker ("lady finger" must find Okra).

## Decision

**1. Users choose ingredients from the catalog. They never send free text.** The app shows the catalog (`GET /api/v1/ingredients`, ADR-0002) and the user ticks what they have. A search request carries ingredient **ids**, not names.

**2. Ingredient ids are stable slugs, taken from the English name when the ingredient is created, and append-only:** lowercase, matching `^[a-z0-9]+(-[a-z0-9]+)*$`, at most 64 characters (`potato`, `curry-leaves`, `coconut-milk`). Once published, an id is never renamed, reused or deleted. Renaming the display name doesn't change the id. Retiring an ingredient sets `retired = true` in the catalog (ADR-0002) instead of removing it. A CI test fails if any id in `main`'s catalog is missing from the changed catalog.

**3. Request validation is membership, not normalization:**
- `ingredient_ids`: 1 to 50 items. Each must match the slug pattern and be an id that has been published in the catalog at some point. An id that was never published returns `422` naming the entry, because only a client bug can produce one.
- A published id that is no longer a main-list ingredient is accepted, never a `422`. A client may be showing a cached catalog, and a catalog change must not break its searches:
  - **retired:** ignored for matching
  - **now class S:** treated as an assumed staple, the same as a ticked staple
  - Both are listed in the response as `ignored_ingredients`, each `{"id", "name", "reason"}` with reason `retired` or `now_staple`. The app uses this to refresh its catalog, and the server counts them as a metric so we can see stale clients.
  - They still count toward the 50-item limit, since the limit bounds request size.
- Duplicate ids are rejected with `422` naming the repeated id. A picker can't tick the same box twice, so a duplicate means a client bug, and failing fast surfaces it. The OpenAPI schema declares `uniqueItems: true`.
- Ids are compared by exact equality. No case folding, trimming or substring matching happens on the request path.

**4. Normalization still exists, in one pure function, for data and search.** `recipe_app.domain.normalization.normalize(text) -> str` applies, in order:

| # | Step | Example: a name typed into the catalog file as `"  Curry   LEAVES "` |
|---|------|-------------------------------------|
| 1 | Unicode NFKC | unchanged |
| 2 | Trim leading and trailing whitespace | `"Curry   LEAVES"` |
| 3 | Collapse inner whitespace to one space | `"Curry LEAVES"` |
| 4 | `str.casefold()` | `"curry leaves"` |

It is never applied to request fields, because requests carry ids. It runs in two places only:
- **Loading the catalog:** the catalog file is typed and edited by hand, so `"Tomato"` and `"tomato "` could be added as two ingredients by mistake. The catalog loader normalizes every display name so the startup check (rule 6) rejects near-duplicate names. It also stores every search term normalized, ready for matching; search terms are not checked for duplicates. Task 2 uses the same loader and function. Seed recipes refer to ingredients by id, so they are checked by id (rule 6), not normalized.
- **The picker's search box:** there is no search endpoint. The app downloads the whole catalog (`GET /api/v1/ingredients`) and filters it on the device. It applies the same steps (trim, collapse spaces, casefold) to what the user types, for example `"Lady Finger "`, before prefix-matching names and search terms. Search only filters what the list shows; the request still sends the id of the item they tick.

**5. One English name per ingredient, in its common form, at one written level of detail.** Use the singular where English uses a singular (`potato`, `okra`) and the natural form otherwise (`cumin-seeds`, `curry-leaves`, `green-chillies`). Never two forms of the same ingredient, and no regional-language names anywhere in the catalog. Each entry may carry `search_terms` for English synonyms and variety names, never regional-language translations, for example Okra has `["lady finger"]` and Coriander leaves has `["cilantro"]`. The picker's search box matches the name and these terms by prefix, so typing "pota" already finds Potato and plurals aren't needed.

**The granularity rule:** two products are **separate ingredients** when using one in place of the other in a recipe changes the dish or makes it fail. Otherwise they are **one ingredient**, and the variants go in its `search_terms`. A reviewer checks a new entry by naming one dish where the swap fails. If nobody can name one, it's one ingredient.

| Family | Decision | Ids | Why |
|---|---|---|---|
| Cumin | split | `cumin-seeds`, `cumin-powder` | recipes call for one or the other, and a user can be out of just one |
| Dal | split | `toor-dal`, `moong-dal`, `masoor-dal`, `chana-dal`, `urad-dal` | cooking times and textures differ; urad is the base of idli batter |
| Rice | split | `rice` (search terms: sona masoori, white rice), `basmati-rice`, `arborio-rice` | biryani needs long grain; risotto needs starchy short grain |
| Cheese | split | `mozzarella`, `parmesan`, `cheddar` | melt and flavour aren't interchangeable; paneer is already its own ingredient |
| Pasta | one | `pasta` (search terms: spaghetti, penne, fusilli, macaroni) | shapes swap freely in home cooking |

A recipe lists the specific variant it was written with. Substitutions ("any dal works") are out of scope for v1.

**6. The catalog is validated at startup, and the app refuses to start if:**
- two ingredients have the same id, or the same normalized display name
- a seed recipe uses an ingredient id that isn't in the catalog

**7. Responses use ids plus display names.** Every ingredient in a response is an object, `{"id": "potato", "name": "Potato"}`, so quantities can be added in v2 without breaking clients (Q4).

## Consequences

- **Easier:** no unknown ingredients, no typos, no alias resolution per request. Matching is set membership on ids, which is trivially fast and testable.
- **Easier:** the old normalization gate tests (`["Tomato", " tomatoes ", "TOMATO"]`) become id tests: unknown id gives `422`, a duplicate id gives `422`, and a staple id in `ingredient_ids` gives `422`.
- **Harder:** the catalog only grows. Retired ingredients stay in the file for good, which is a few hundred rows at most. That's the price of never breaking an installed app.
- **Harder:** a user with moong dal won't match a toor dal recipe even when they would happily swap. That's deliberate, because a wrong match is worse than a missed one. Recipe-level substitutes need their own ADR if users ask for them.
- **Retired:** the "regional alias" gate test (`["aloo", "bhindi"]` scores the same as `["potato", "okra"]`) and the locked aloo/bhindi/jeera alias decision. A user who searches in Hindi finds nothing, which is an accepted v1 trade-off; regional search terms can be added later without changing any id.
- **Supersedes** the free-text answers to Q5 and Q13 and the `unrecognized_ingredients` field. Typing a staple is impossible now, because staples aren't offered in the main list (aromatics such as onion, garlic and tomato live only in the staples list, ADR-0002).
- **Revisit when:** users regularly look for ingredients the catalog lacks. A "suggest an ingredient" flow would get its own ADR.
