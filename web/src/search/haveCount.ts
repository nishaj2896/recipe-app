/**
 * How many of a recipe's ingredients this kitchen has: the pantry plus the
 * staples it isn't out of. Worked out on the device, so search never sends
 * the pantry (ADR-0012 rule 10).
 */
export function haveCount(
  ingredientIds: readonly string[],
  pantry: ReadonlySet<string>,
  staples: ReadonlySet<string>,
  outOfStaples: ReadonlySet<string>,
): number {
  return ingredientIds.filter(
    (id) => pantry.has(id) || (staples.has(id) && !outOfStaples.has(id)),
  ).length;
}
