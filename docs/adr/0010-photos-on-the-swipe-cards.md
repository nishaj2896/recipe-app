# ADR-0010: The swipe card shows the dish photo

- Status: Accepted
- Date: 2026-10-30
- Deciders: Nisha
- Amends: ADR-0008 rule 7 (search cards gain the photo; they were left unchanged to keep a deck small), ADR-0008 rule 8 (the photo is on the card as well as the recipe screen)
- Related: ADR-0007 (the search reads recipe rows), ADR-0009 (the card already carries `plan_ahead` the same way)

## Context

ADR-0008 put the photo on the recipe screen only, and drew a tinted bowl on the swipe card. Once the first photos were in, Nisha opened the app and found the card still showed the bowl: the photo appeared only after opening the recipe. The card is where a cook decides, so the photo belongs there.

## Decision

**1. Each search card carries `image`.** It is the same `{ "url", "alt" }` object as on the recipe detail, with the same versioned `/dishes/<file>?v=<first 12 hex of sha256>` URL, or `null` for a recipe without a photo. The URL is built in one place, so a card and its recipe screen always agree, and a regenerated photo is a new URL on both.

**2. It rides on the recipe row.** `recipes.image_file`, `image_sha256` and `image_alt` already exist (ADR-0008 rule 5). The search already reads the recipe row for each card in the page, so three more short columns add no query and change no ranking query or index (ADR-0007). A deck stays small: the card carries a path, not the photo.

**3. The card shows the photo where the bowl was.** The ingredient drawings stay on top of it, and the match ring stays at the bottom, as before. A recipe without a photo, or a photo that fails to load, shows the drawn bowl, as the recipe screen already does.

## Consequences

- **Easier:** the first thing a cook sees is the dish, not a drawing.
- **Harder:** each card shown loads one image of up to 150 KB. The deck draws only the top few cards at a time, so a cook downloads a few photos up front and one more with each swipe, not the whole deck at once, and `/dishes/` is cached for a year (ADR-0008 rule 6). If that feels slow on a phone, the next step is a smaller card-sized file beside the 800 × 800 one.
- **Deferred:** a card-sized thumbnail, and preloading the next card's photo.
