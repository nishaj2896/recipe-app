import { Link } from "react-router";

import { DEFAULT_RESULTS, searchable, useRecipeSearch } from "../api/queries";
import { RecipeRow } from "./RecipeRow";
import styles from "./RecipeResults.module.css";
import { useDebounced } from "./useDebounced";
import { useKitchen } from "./useKitchen";

/**
 * The best recipe matches under the pantry's search box, and "See all" for
 * the rest (ADR-0012 rules 10 and 11). The ingredient tiles below stay as
 * they were, so the box finds both.
 */
export function RecipeResults({ text }: { text: string }) {
  const settled = useDebounced(text.trim());
  const found = useRecipeSearch(settled, DEFAULT_RESULTS);
  const { rules, have } = useKitchen();
  if (!searchable(settled)) return null;
  const total = found.data?.total ?? 0;

  return (
    <section className={styles.results} aria-labelledby="recipe-results-title">
      <h2 id="recipe-results-title" className={styles.title}>
        Recipes
      </h2>
      {found.isError && (
        <p className={styles.status} role="alert">
          We couldn't search recipes just now.
        </p>
      )}
      {found.data && total === 0 && (
        <p className={styles.status}>No recipe matches “{settled}”.</p>
      )}
      <ul className={styles.list}>
        {(found.data?.results ?? []).map((recipe) => (
          <li key={recipe.id}>
            <RecipeRow recipe={recipe} have={have(recipe.ingredient_ids)} rules={rules} />
          </li>
        ))}
      </ul>
      {total > (found.data?.results.length ?? 0) && (
        <Link
          to={`/search?${new URLSearchParams({ q: settled }).toString()}`}
          className={styles.seeAll}
        >
          See all {total} recipes
        </Link>
      )}
    </section>
  );
}
