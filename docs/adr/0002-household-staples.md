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
| A | Main character | 1.0 | Main list, unticked by default | paneer, chicken, eggs, potato, rice, dal, coconut milk, pasta |
| B | Supporting cast | 0.5 | Main list, unticked by default | peas, bell pepper, mushroom, cream, curd, cheese, milk |
| S | Staple, kind *fresh* | assumed; 0.25 if unticked | Staples list, ticked by default | tomato, onion, garlic, ginger, green chillies, curry leaves, coriander leaves, lemon |
| S | Staple, kind *pantry* | assumed; 0.25 if unticked | Staples list, ticked by default | salt, sugar, water, oil, ghee, butter, black pepper, turmeric, cumin seeds, cumin powder, curry powder |

Fresh and pantry staples behave identically. `kind` only groups the staples screen.

**2. The classification rule.** Ask in order and stop at the first yes:
1. Is it a seasoning, fat, sweetener, dry spice or water that a typical home kitchen of our v1 users (Indian households) keeps on the shelf by default? → **S, pantry**
2. Is it a fresh flavour base that the same kitchen restocks every week and uses in small amounts to flavour many dishes? → **S, fresh**
3. Does it define the dish, so that removing it makes a different dish? → **A**
4. Otherwise → **B**

Worked examples: ginger passes 2 (S, fresh). Paneer fails 1 and 2, then passes 3 (A). Milk and curd are restocked weekly but used in volume, not in small amounts to flavour, so they fail 2 and land in **B**: always core, never assumed. Coconut milk isn't kept by default in a *typical* kitchen, and it defines the curries that use it (A).

**3. Milk and curd are never staples.** This is a product decision (14 Oct). A test asserts neither is class S.

**4. Behaviour:**

| Class | Ticked | Not ticked |
|---|---|---|
| A, B | Core, matched | Core, missing |
| S | Assumed: not scored, never missing, listed in `assumed_staples` | Sent in `excluded_staples`: core at W = 0.25, listed as missing |

**5. Staples are server policy with one client override.** The server decides which ingredients are staples. The client can only *subtract* staples, by unticking them, which sends them in `excluded_staples`. That field is a list of 0 to 100 ingredient ids, and each must be a class S id or the request fails with `422` naming the entry. Duplicates are rejected with `422` too, the same rule as `ingredient_ids` (ADR-0001). The app remembers unticked staples on the device (no accounts in v1) and sends them with every search.

**6. Diet is computed, never hand-labelled.** Every ingredient has one diet tag, from this ordered list: `vegan` < `vegetarian` < `egg` < `non_veg`. Eggs are `egg`. Ghee, butter, milk, curd, paneer and cream are `vegetarian`. Chicken, meat and fish are `non_veg`. A recipe's diet is the highest tag across **all** its ingredients, assumed staples included. So a dal finished with assumed ghee is `vegetarian` and never appears in a vegan search, and an egg curry is `egg`.

The `diet` filter is hierarchical: it returns recipes whose diet is at or below the requested level.

| `diet` requested | Returns recipes tagged |
|---|---|
| `vegan` | vegan |
| `vegetarian` | vegan, vegetarian |
| `egg` | vegan, vegetarian, egg |
| `non_veg` or omitted | all |

Tests: an egg curry is returned for `egg` and `non_veg`, and never for `vegetarian` or `vegan`. A chicken curry is returned only for `non_veg`.

**7. One catalog file, versioned and validated.** `data/ingredients.v1.toml` lists every ingredient with `id`, `name`, `class`, `kind` (class S only), `diet`, `category` and `search_terms` (ADR-0001). It's loaded once at startup into an immutable `IngredientCatalog` domain object. The app refuses to start if:
- the file is empty, or any id or normalized name is duplicated
- an ingredient has an unknown class, kind or diet tag
- milk or curd is class S
- a seed recipe uses an id that isn't in the catalog

Changing an ingredient's class is a reviewed PR. Changing the rule needs a new ADR.

**8. Read endpoints:**
- `GET /api/v1/ingredients` returns the whole catalog: id, name, class, kind, category, diet and search_terms, ordered by category then name.
- `GET /api/v1/staples` returns class S only, grouped by kind and category, in the same stable order.
- Both are bounded reference data (under 1,000 items), so they return the full list in one response with an `ETag` and `Cache-Control: public, max-age=3600`, instead of paginating. This is a deliberate, documented exception to "pagination on every collection", to revisit if the catalog passes 2,000 items.

**9. Every search result lists its assumed staples** in `assumed_staples`, as `{id, name}` objects, so the user can see what was taken for granted.

## Consequences

- **Easier:** one data file drives the picker, the staples screen, weights and diet. Two classes of behaviour (core or staple) instead of four.
- **Easier:** a staple can't be "typed" any more, so the old questions about typed staples (Q13) and promoted aromatics disappear.
- **Changed from earlier drafts:** aromatics no longer score 0.25 when the user has them. They're assumed when ticked, which is the default, and core at 0.25 only when unticked.
- **Accepted trade-off:** the staples list reflects a typical Indian household kitchen, while recipes can be any cuisine. A pasta recipe still assumes the same salt, oil and garlic. Kitchens that differ will disagree with some classes until per-user staple defaults exist.
- **Changed from the locked table:** egg is its own diet level instead of `non_veg`, so eggetarian users get egg dishes without meat.
- **Revisit when:** user accounts exist. A user's own staples list could then replace the global default.
