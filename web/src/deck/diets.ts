import type { RecipeCard } from "../api/client";

/** How each diet reads on a card or a recipe. */
export const DIETS: Record<RecipeCard["diet"], string> = {
  vegan: "Vegan",
  vegetarian: "Vegetarian",
  egg: "Has egg",
  non_veg: "Non-veg",
};
