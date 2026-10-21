import type { IngredientRef, RecipeCard } from "../api/client";

export interface ShoppingItem {
  ingredient: IngredientRef;
  /** How many of the saved recipes need it. */
  recipes: number;
}

/** What to buy to cook the saved recipes: the most-needed first. */
export function shoppingList(saved: readonly RecipeCard[]): ShoppingItem[] {
  const items = new Map<string, ShoppingItem>();
  for (const card of saved) {
    for (const ingredient of card.missing_ingredients) {
      const item = items.get(ingredient.id);
      if (item) item.recipes += 1;
      else items.set(ingredient.id, { ingredient, recipes: 1 });
    }
  }
  return [...items.values()].sort(
    (a, b) => b.recipes - a.recipes || a.ingredient.name.localeCompare(b.ingredient.name),
  );
}

/** The list as plain text, for sharing to a notes or messaging app. */
export function shoppingText(items: readonly ShoppingItem[]): string {
  return ["Shopping list", ...items.map((item) => `- ${item.ingredient.name}`)].join(
    "\n",
  );
}
