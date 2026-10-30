# ADR-0009: Recipes that need a long wait say "Plan ahead"

- Status: Accepted
- Date: 2026-10-30
- Deciders: Nisha
- Amends: ADR-0003 rule 10 (a long wait is now recorded beside the times, not only in the steps), ADR-0008 rule 7 (the recipe detail and the search cards gain one field)
- Related: ADR-0005 (the sync), ADR-0007 (the search reads recipe rows), issue #85

## Context

Since ADR-0003 rule 10 was amended on 30 Oct 2026, prep and cook time count hands-on work only. Soaking, fermenting, marinating, resting, chilling and freezing are left out. That keeps the card honest about how long you are busy, but it hides something else: idli shows about 30 minutes although the batter needs an overnight soak and ferment, and kulfi shows its hands-on time although it needs 6 hours in the freezer. A cook who swipes right at 6 pm should know that dinner is tomorrow.

## Decision

**1. Each recipe may carry one `plan_ahead` table.** In a recipe file it looks like `plan_ahead = { wait_minutes = 480, note = "soak overnight" }`. Most recipes have none. `wait_minutes` is the total, in whole minutes, of the hands-off waits that each last an hour or more. A recipe with a soak and a ferment (idli) gets both added up, because that is what the cook has to plan around; short rests along the way do not count. A stored value was chosen over deriving it from the steps: a step is prose, and a wrong guess about "leave for 2 hours" would put a wrong label on a card.

**2. The label shows from one hour.** `wait_minutes` must be from 60 to 10,080 (one week). Under an hour a wait fits around the cooking, so it adds nothing to `wait_minutes`, and a recipe with no wait of an hour or more has no `plan_ahead`. A table with a wait under 60 is rejected when the file is loaded, so the rule has one meaning everywhere. This rule counts only the wait the cook cannot hurry. The steps still say how long every wait takes (ADR-0003 rule 10).

**3. The label says what to do, not only how long.** `note` finishes the sentence "Plan ahead: ". It is 1 to 40 characters, single-spaced, does not start with a capital letter and has no full stop, for example "soak overnight" or "marinate for 2 hours". The card shows "Plan ahead: soak overnight". The recipe screen adds the length of the wait in hours or days, and says it is not counted in the times above.

**4. The database and the API carry it.** One migration adds `recipes.wait_minutes` and `recipes.wait_note`, both NULL for most recipes and NULL together, with CHECKs for the range and the note length. The sync writes them on every run like the rest of a recipe. Search cards and the recipe detail both gain `plan_ahead` (`{ "wait_minutes", "note" }` or `null`). Cards need it because that is where the cook decides. It rides on the recipe row the search already reads, so there is no extra query, and no search query or index changes (ADR-0007). Adding a field keeps both responses in `/api/v1`. Until a sync writes the columns, `plan_ahead` is `null` and no card shows a label.

**5. The data arrives in a second pull request.** The loader, database, API and web screens come first, with no recipe using the field. A separate data pull request then adds `plan_ahead` to the recipes that need it, checked by the loader like every other recipe change.

## Consequences

- **Easier:** a cook sees at a glance which dishes need tomorrow's planning, and the hands-on times stay honest.
- **Harder:** an author must write the wait down as well as in the steps, and the two can drift apart. The data pull request checks every recipe whose steps mention a wait of an hour or more; nothing checks that automatically afterwards.
- **Deferred:** filtering the deck by "ready tonight", and a "total including waiting" time.
