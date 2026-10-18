# ADR-0004: Coconut products are filed by what they are used as

- Status: Accepted
- Date: 2026-10-18
- Deciders: Nisha
- Supersedes: ADR-0002 rule 10, tie-break 6 ("Coconut in any form goes in `nuts-seeds-and-dried-fruit` …")
- Related: ADR-0002 (categories)

## Context

ADR-0002 rule 10, tie-break 6, puts "coconut in any form" in `nuts-seeds-and-dried-fruit`, except coconut milk and coconut cream. Taken literally, that files coconut oil next to almonds instead of with the other oils, and coconut sugar and coconut flour next to raisins. A cook looking for coconut oil opens Oils & fats first, so the literal rule hides the item from the person looking for it. ADR-0002 says changing a tie-break rule needs a new ADR.

## Decision

Tie-break 6 is replaced by:

6. Coconut flesh in any form (fresh, grated, desiccated, dried, tender) and coconut butter go in `nuts-seeds-and-dried-fruit`. Coconut milk and coconut cream go in `plant-based-milks`. Any other product made from coconut goes where the same product from another source would go: coconut oil in `oils-and-fats`, coconut sugar in `sweeteners`, coconut flour in `flours-and-baking`.

The other tie-break rules are unchanged. The rule still never overlaps another: tie-break 2 (dairy first) can't apply to coconut, and tie-break 4 already files milled products in `flours-and-baking`.

## Consequences

- **Easier:** each coconut product appears in the group a cook checks first, and new ones need no special case ("where would the same product from another source go?").
- **Unchanged:** category ids, the catalog schema and the loader checks. This ADR changes where three ingredients are filed, nothing else.
