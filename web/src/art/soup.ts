/** Soup colours a dish can take: warm, so every card looks good to eat. */
const SOUPS = ["#f2b233", "#e8742a", "#c9502c", "#9bbf3a", "#f0d27a", "#d9932f"];

/** Picks the same soup colour for a recipe every time. */
export function soupFor(recipeId: string): string {
  let hash = 0;
  for (const char of recipeId) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return SOUPS[hash % SOUPS.length] ?? "#f2b233";
}
