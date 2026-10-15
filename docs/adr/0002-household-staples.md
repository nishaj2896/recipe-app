# ADR-0002: Ingredient classes and household staples are server-owned catalog data

- Status: Accepted
- Date: 2026-10-15
- Deciders: Nisha
- Supersedes: "Egg is non-veg" and the three-level diet filter in the Task 1 "Product decisions locked" table
- Related: ADR-0001 (catalog and ids), ADR-0003 (weighted scoring)

## Context

Users don't think of household staples as "ingredients I have": salt, spice powders, oil, ghee, onion, garlic and tomato are simply in the kitchen. If recipes list them as missing, almost every recipe looks impossible to cook. Recipes can come from any cuisine, so the catalog must hold ingredients for pasta and stir-fries as well as dal. But assuming them must stay honest: a user who is out of turmeric has to be able to say so, and a vegan must never be shown a dish that relies on assumed ghee. Users now pick ingredients from a catalog (ADR-0001), so the catalog is also where staples, weights and diet tags live. Classification must be repeatable: anyone should be able to classify `paneer` or `coconut milk` from the written rule.

## Decision

**1. Every catalog ingredient has exactly one class:**

| Class | Name | Weight | In the app | Examples |
|---|---|---|---|---|
| A | Main character | 1.0 | Main list, unticked by default | paneer, chicken, egg, potato, rice, basmati rice, toor dal, moong dal, coconut milk, pasta |
| B | Supporting cast | 0.5 | Main list, unticked by default | peas, bell pepper, mushroom, cream, curd, mozzarella, parmesan, milk |
| S | Staple, kind *fresh* | assumed; 0.25 if unticked | Staples list, ticked by default | tomato, onion, garlic, ginger, green chillies, curry leaves, coriander leaves, lemon |
| S | Staple, kind *pantry* | assumed; 0.25 if unticked | Staples list, ticked by default | salt, sugar, water, oil, ghee, butter, black pepper, turmeric, cumin seeds, cumin powder, curry powder |

Fresh and pantry staples behave identically. `kind` only groups the staples screen.

**2. The classification rule.** Ask in order and stop at the first yes:
1. Is it a seasoning, fat, sweetener, dry spice or water that a typical home kitchen of our v1 users (Indian households) keeps on the shelf by default? → **S, pantry**
2. Is it a fresh flavour base that the same kitchen restocks every week and uses in small amounts to flavour many dishes? → **S, fresh**
3. Does it define the dish, so that removing it makes a different dish? → **A**
4. Otherwise → **B**

Worked examples: ginger passes 2 (S, fresh). Paneer fails 1 and 2, then passes 3 (A). Milk and curd are restocked weekly but used in volume, not in small amounts to flavour, so they fail 2 and land in **B**: always core, never assumed. Coconut milk isn't kept by default in a *typical* kitchen, and it defines the curries that use it (A).

**3. Milk and curd are never staples.** This is a product decision (14 Oct). Their ids live in one named constant, `NEVER_STAPLES = frozenset({"milk", "curd"})`, in `recipe_app.domain.catalog` next to the loader check. The loader rejects a catalog that makes either of them class S, and the test imports the same constant, so the rule and its test can't drift apart.

**4. Behaviour:**

| Class | Ticked | Not ticked |
|---|---|---|
| A, B | Core, matched | Core, missing |
| S | Assumed: not scored, never missing, listed in `assumed_staples` | Sent in `excluded_staples`: core at W = 0.25, listed as missing |

**5. Staples are server policy with one client override.** The server decides which ingredients are staples. The client can only *subtract* staples, by unticking them, which sends them in `excluded_staples`. That field is a list of 0 to 100 ingredient ids. An id that was never published returns `422` naming the entry, and so does a duplicate (the same rule as `ingredient_ids`, ADR-0001). A published id that is no longer class S, because it was retired or moved to class A or B, is ignored and listed in `ignored_ingredients` (ADR-0001 rule 3). The app remembers unticked staples on the device (no accounts in v1) and sends them with every search.

**6. Diet is computed, never hand-labelled.** Every ingredient has one diet tag, from this ordered list: `vegan` < `vegetarian` < `egg` < `non_veg`. Eggs are `egg`. Ghee, butter, milk, curd, paneer and cream are `vegetarian`. Chicken, meat and fish are `non_veg`. A recipe's diet is the highest tag across **all** its ingredients, assumed staples included. So a dal finished with assumed ghee is `vegetarian` and never appears in a vegan search, and an egg curry is `egg`.

The `diet` filter is hierarchical: it returns recipes whose diet is at or below the requested level.

| `diet` requested | Returns recipes tagged |
|---|---|
| `vegan` | vegan |
| `vegetarian` | vegan, vegetarian |
| `egg` | vegan, vegetarian, egg |
| `non_veg` or omitted | all |

Tests: an egg curry is returned for `egg` and `non_veg`, and never for `vegetarian` or `vegan`. A chicken curry is returned only for `non_veg`.

**7. One catalog file, versioned and validated.** `data/ingredients.v1.toml` lists every ingredient ever published, with `id`, `name`, `class`, `kind` (class S only), `diet`, `category`, `search_terms` (ADR-0001) and `retired` (default `false`). The `v1` in the name is the **schema** version: the fields and what they mean. Adding, editing or retiring an ingredient is an ordinary edit to the same file. A `v2` file is needed only when a field is added, removed or changes meaning, and that change needs its own ADR. Each content version is identified by the SHA-256 hash of the file, computed at load as `IngredientCatalog.content_hash` and logged at startup, so you can always tell which catalog a running pod has. The file is loaded once at startup into an immutable `IngredientCatalog` domain object. The app refuses to start if:
- the file is empty, or any id or normalized name is duplicated
- an ingredient has an unknown class, kind or diet tag
- an id in `NEVER_STAPLES` is class S
- a seed recipe uses an id that isn't in the catalog, or one that is retired (replace the ingredient or retire the recipe first)

**The same checks run in CI.** One test loads `data/ingredients.v1.toml` and the seed recipes through the real loader, so a catalog that would stop the app from starting can't be merged. The loader is the only place these rules are written, and the test just calls it. Together with the append-only check (ADR-0001 rule 2), a data PR is validated as strictly as a code PR, and a bad catalog is caught in review instead of during a deploy.

Changing an ingredient's class is a reviewed PR. Changing the rule needs a new ADR.

**8. Read endpoints:**
- `GET /api/v1/ingredients` returns every ingredient that isn't retired: id, name, class, kind, category, diet and search_terms, ordered by category then name.
- `GET /api/v1/staples` returns class S ingredients that aren't retired, grouped by kind and category, in the same stable order.
- Both are bounded reference data (under 1,000 items), so they return the full list in one response instead of paginating. This is a deliberate, documented exception to "pagination on every collection", to revisit if the catalog passes 2,000 items.
- **Caching:** both send `Cache-Control: public, no-cache` and a strong `ETag`. `no-cache` means "store it, but check before reusing it". The client sends `If-None-Match` on every load, and an unchanged catalog costs a `304 Not Modified` with no body.
- **The ETag is the SHA-256 of the serialized response body,** quoted (`"sha256-…"`), computed once when the catalog is loaded. It is never a file modification time or a per-process counter, so every pod returns the same ETag for the same content. That only holds if serialization is deterministic: fixed field order, the stable sort above, and no timestamps in the body. A test asserts that two independently loaded catalogs give the same ETag. This is a different value from `content_hash` (rule 7), which identifies the catalog file. The ETag identifies one endpoint's response.
- **Freshness target:** a catalog change reaches each client on its next catalog request, which the app makes on every launch and at least every 24 hours while running. The app sends its catalog ETag as `X-Catalog-Version` on every search. The server records the share of searches on an old version, and the share that return `ignored_ingredients` (ADR-0001 rule 3). An alert fires if more than 5% of searches are still on an old catalog 24 hours after a catalog deploy.

**9. Every search result lists its assumed staples** in `assumed_staples`, as `{id, name}` objects, so the user can see what was taken for granted.

## Consequences

- **Easier:** one data file drives the picker, the staples screen, weights and diet. Two classes of behaviour (core or staple) instead of four.
- **Easier:** a staple can't be "typed" any more, so the old questions about typed staples (Q13) and promoted aromatics disappear.
- **Harder:** every app launch makes one catalog request, even when nothing changed. It's a `304` with no body, so the cost is one round trip, and in exchange there's no window where a client shows a catalog that's an hour old.
- **Changed from earlier drafts:** aromatics no longer score 0.25 when the user has them. They're assumed when ticked, which is the default, and core at 0.25 only when unticked.
- **Accepted trade-off:** the staples list reflects a typical Indian household kitchen, while recipes can be any cuisine. A pasta recipe still assumes the same salt, oil and garlic. Kitchens that differ will disagree with some classes until per-user staple defaults exist.
- **Changed from the locked table:** egg is its own diet level instead of `non_veg`, so eggetarian users get egg dishes without meat.
- **Revisit when:** user accounts exist. A user's own staples list could then replace the global default.
