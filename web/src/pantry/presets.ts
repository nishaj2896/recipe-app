import presets from "./presets.json";

/**
 * Ingredient lists the pantry offers before the user types anything. They
 * live in JSON so the Python tests can check every id against the catalog
 * (tests/test_web_presets.py).
 */

/** What the pantry grid shows before the user types or picks a category. */
export const POPULAR: readonly string[] = presets.popular;

export interface QuickStart {
  id: string;
  name: string;
  ingredientIds: readonly string[];
}

/** One tap fills the pantry with a typical kitchen. */
export const QUICK_STARTS: readonly QuickStart[] = presets.quick_starts.map((preset) => ({
  id: preset.id,
  name: preset.name,
  ingredientIds: preset.ingredient_ids,
}));
