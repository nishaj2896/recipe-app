import { Link } from "react-router";

import type { FoundRecipe } from "../api/client";
import { DishPhoto } from "../art/DishPhoto";
import { DishArt } from "../art/IngredientArt";
import { DIETS } from "../deck/diets";
import { breaks, type FoodRules } from "../rules/check";
import { ALLERGENS, CUISINES } from "../rules/labels";
import styles from "./RecipeRow.module.css";

/** Whether this kitchen has most of the recipe: the count reads green. */
const MOSTLY = 0.75;

/**
 * One search result: the dish, its cuisine and time, how much of it this
 * kitchen has and, in red, what in it breaks the food rules. Search shows
 * every recipe (ADR-0012 rule 4), so the row says so rather than hiding it.
 */
export function RecipeRow({
  recipe,
  have,
  rules,
}: {
  recipe: FoundRecipe;
  have: number;
  rules: FoodRules;
}) {
  const total = recipe.ingredient_ids.length;
  const broken = breaks(recipe, rules);
  const warnings = [
    ...broken.allergens.map(
      (allergen) => `Contains ${ALLERGENS[allergen].toLowerCase()}`,
    ),
    ...(broken.ingredientIds.length > 0 ? ["Has an ingredient you avoid"] : []),
    ...(broken.diet || broken.jain ? ["Not for your diet"] : []),
  ];
  const meta = [
    recipe.cuisine ? CUISINES[recipe.cuisine] : null,
    `${String(recipe.total_minutes)} min`,
    recipe.diet === "vegan" || recipe.diet === "vegetarian" ? null : DIETS[recipe.diet],
  ].filter((part) => part !== null);

  return (
    <Link to={`/recipe/${recipe.id}`} className={styles.row}>
      {recipe.image ? (
        <DishPhoto
          {...recipe.image}
          alt=""
          recipeId={recipe.id}
          className={styles.photo}
          artSize={52}
        />
      ) : (
        <span className={styles.art}>
          <DishArt recipeId={recipe.id} size={52} />
        </span>
      )}
      <span className={styles.text}>
        <span className={styles.name}>{recipe.name}</span>
        <span className={styles.meta}>
          {meta.join(" · ")} ·{" "}
          <span
            className={styles.have}
            data-mostly={(total > 0 && have >= total * MOSTLY) || undefined}
          >
            have {have} of {total}
          </span>
        </span>
        {warnings.map((warning) => (
          <span key={warning} className={styles.warning}>
            {warning}
          </span>
        ))}
      </span>
    </Link>
  );
}
