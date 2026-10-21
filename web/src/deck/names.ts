import type { IngredientRef } from "../api/client";

const SHOWN_NAMES = 3;

/** "paneer, peas, tomato and 2 more" */
export function listNames(items: readonly IngredientRef[]): string {
  const names = items.slice(0, SHOWN_NAMES).map((item) => item.name.toLowerCase());
  const more = items.length - names.length;
  return more > 0 ? `${names.join(", ")} and ${String(more)} more` : names.join(", ");
}
