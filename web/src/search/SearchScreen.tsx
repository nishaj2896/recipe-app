import { useSearchParams } from "react-router";

import { searchable, useAllRecipeResults, useCatalog } from "../api/queries";
import { BackArrow } from "../app/BackArrow";
import { useLeave } from "../app/leave";
import { searchIngredients } from "../pantry/search";
import { useDevice } from "../store/device";
import { RecipeRow } from "./RecipeRow";
import styles from "./SearchScreen.module.css";
import { useDebounced } from "./useDebounced";
import { useKitchen } from "./useKitchen";

/** Ingredient matches shown above the recipes, to add to the pantry. */
const INGREDIENT_MATCHES = 6;

/**
 * Search on its own screen: from the deck and the cookbook, and "See all"
 * from the pantry (ADR-0012 rules 10 and 11). Every match, 20 at a time;
 * each row opens the recipe, where it can be saved.
 */
export function SearchScreen() {
  const [params, setParams] = useSearchParams();
  const text = params.get("q") ?? "";
  const leave = useLeave();
  const catalog = useCatalog();
  const pantry = useDevice((state) => state.pantry);
  const { addToPantry, removeFromPantry } = useDevice.getState();
  const { rules, have } = useKitchen();
  const results = useAllRecipeResults(useDebounced(text.trim()));
  const ingredients = searchIngredients(catalog.data ?? [], text, INGREDIENT_MATCHES);
  const recipes = (results.data?.pages ?? []).flatMap((page) => page.results);
  const total = results.data?.pages[0]?.total;
  const count =
    total === undefined
      ? "Recipes"
      : total === 0
        ? `No recipe matches “${text.trim()}”`
        : `${String(total)} ${total === 1 ? "recipe" : "recipes"}`;
  // Search pages stop at offset 200 (ADR-0012 rule 11), so a broad word
  // lists fewer than it finds: say so where the list ends.
  const capped = total !== undefined && !results.hasNextPage && recipes.length < total;

  return (
    <main className={styles.screen}>
      <h1 className={styles.visuallyHidden}>Search recipes</h1>
      <div className={styles.top}>
        <button type="button" className={styles.back} aria-label="Back" onClick={leave}>
          <BackArrow />
        </button>
        <input
          type="search"
          className={styles.input}
          placeholder="Search recipes or ingredients"
          aria-label="Search recipes or ingredients"
          // The screen exists to type into.
          autoFocus={text === ""}
          maxLength={60}
          value={text}
          onChange={(event) => {
            setParams(event.target.value ? { q: event.target.value } : {}, {
              replace: true,
            });
          }}
        />
      </div>

      {ingredients.length > 0 && (
        <section aria-labelledby="ingredients-title" className={styles.section}>
          <h2 id="ingredients-title" className={styles.eyebrow}>
            Ingredients · tap to add to pantry
          </h2>
          <div className={styles.chips}>
            {ingredients.map((item) => {
              const has = pantry.includes(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  className={styles.chip}
                  aria-pressed={has}
                  onClick={() => {
                    if (has) removeFromPantry(item.id);
                    else addToPantry([item.id]);
                  }}
                >
                  <span aria-hidden="true">{has ? "✓" : "+"}</span> {item.name}
                </button>
              );
            })}
          </div>
        </section>
      )}

      {searchable(text) && (
        <section aria-labelledby="recipes-title" className={styles.section}>
          <h2 id="recipes-title" className={styles.eyebrow}>
            {count}
          </h2>
          <p className={styles.visuallyHidden} role="status">
            {count}
          </p>
          {results.isError && (
            <p className={styles.status} role="alert">
              We couldn't search just now.{" "}
              <button
                type="button"
                className={styles.retry}
                onClick={() => {
                  void results.refetch();
                }}
              >
                Try again
              </button>
            </p>
          )}
          <ul className={styles.list}>
            {recipes.map((recipe) => (
              <li key={recipe.id}>
                <RecipeRow
                  recipe={recipe}
                  have={have(recipe.ingredient_ids)}
                  rules={rules}
                />
              </li>
            ))}
          </ul>
          {results.hasNextPage && (
            <button
              type="button"
              className={styles.more}
              disabled={results.isFetchingNextPage}
              onClick={() => {
                void results.fetchNextPage();
              }}
            >
              {results.isFetchingNextPage ? "Loading…" : "Show more"}
            </button>
          )}
          {capped && (
            <p className={styles.status}>
              Showing the first {recipes.length}. Add a word to narrow it down.
            </p>
          )}
        </section>
      )}
      {!searchable(text) && (
        <p className={styles.status}>
          Type a dish, an ingredient or a cuisine: “paneer”, “thai”, “biryani”.
        </p>
      )}
    </main>
  );
}
