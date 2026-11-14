import type { Allergen, DeviceData, Diet } from "../store/device";

export type FoodRules = Pick<
  DeviceData,
  "diet" | "jain" | "avoidAllergens" | "avoidIngredients"
>;

/** What the app knows about a recipe to check it against the food rules. */
export interface Checkable {
  diet: Diet;
  jain: boolean;
  allergens: readonly Allergen[];
  ingredient_ids: readonly string[];
}

/** Each diet lets through itself and every stricter one (ADR-0002 rule 6). */
const ALLOWED: Record<Diet, readonly Diet[]> = {
  non_veg: ["non_veg", "egg", "vegetarian", "vegan"],
  egg: ["egg", "vegetarian", "vegan"],
  vegetarian: ["vegetarian", "vegan"],
  vegan: ["vegan"],
};

/** Where a recipe breaks the food rules; all empty when it keeps them. */
export interface Breaks {
  diet: boolean;
  jain: boolean;
  allergens: Allergen[];
  ingredientIds: string[];
}

/** The same test the deck runs on the server (ADR-0012 rule 4), on the device. */
export function breaks(recipe: Checkable, rules: FoodRules): Breaks {
  return {
    diet: rules.diet !== null && !ALLOWED[rules.diet].includes(recipe.diet),
    jain: rules.jain && !recipe.jain,
    allergens: rules.avoidAllergens.filter((item) => recipe.allergens.includes(item)),
    ingredientIds: rules.avoidIngredients.filter((id) =>
      recipe.ingredient_ids.includes(id),
    ),
  };
}

export function keepsRules(recipe: Checkable, rules: FoodRules): boolean {
  const found = breaks(recipe, rules);
  return (
    !found.diet &&
    !found.jain &&
    found.allergens.length === 0 &&
    found.ingredientIds.length === 0
  );
}
