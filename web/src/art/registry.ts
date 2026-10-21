import registry from "./registry.json";

/**
 * Which drawing each ingredient gets (ADR-0006 rule 8). An ingredient with its
 * own icon uses it; any other falls back to its category's icon. Swapping the
 * art style later is a change to registry.json and sprite.svg, not to the
 * screens. tests/test_web_presets.py checks the ids against the catalog.
 */
export const INGREDIENT_ART: Readonly<Record<string, string>> = registry.ingredients;
export const CATEGORY_ART: Readonly<Record<string, string>> = registry.categories;

/** Used only for a category the app doesn't know yet. */
export const DEFAULT_ART = "produce";

export function artFor(ingredientId: string, categoryId: string): string {
  return INGREDIENT_ART[ingredientId] ?? CATEGORY_ART[categoryId] ?? DEFAULT_ART;
}
