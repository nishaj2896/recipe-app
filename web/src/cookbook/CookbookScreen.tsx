import { useQueries } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { recipeQuery } from "../api/queries";
import { DishArt } from "../art/IngredientArt";
import { DIETS } from "../deck/diets";
import { InstallNudge } from "../install/InstallNudge";
import { useDevice } from "../store/device";
import styles from "./CookbookScreen.module.css";

/** Every recipe the user saved, newest first. */
export function CookbookScreen() {
  const saved = useDevice((state) => state.saved);
  const pantry = useDevice((state) => state.pantry);
  const hydration = useDevice((state) => state.hydration);
  const { unsaveRecipe, clearSaved, restoreSaved } = useDevice.getState();
  const newestFirst = [...saved].reverse();
  const recipes = useQueries({ queries: newestFirst.map((id) => recipeQuery(id)) });
  // The last removal, so it can be undone: what it said, and the list before it.
  const [removal, setRemoval] = useState<{ message: string; before: string[] } | null>(
    null,
  );

  function remove(id: string, name: string | undefined) {
    setRemoval({ message: `Removed ${name ?? "a recipe"}.`, before: [...saved] });
    unsaveRecipe(id);
  }

  function removeAll() {
    const count = saved.length;
    setRemoval({
      message: `Removed ${String(count)} ${count === 1 ? "recipe" : "recipes"}.`,
      before: [...saved],
    });
    clearSaved();
  }

  return (
    <main className={styles.screen}>
      <header className={styles.header}>
        <Link to="/" className={styles.back} aria-label="Back to your pantry">
          <span aria-hidden="true">←</span>
        </Link>
        <h1 className={styles.title}>Your cookbook</h1>
        {saved.length > 0 && (
          <button type="button" className={styles.clear} onClick={removeAll}>
            Remove all
          </button>
        )}
      </header>

      <InstallNudge />

      <div role="status" className={styles.undoSlot}>
        {removal && (
          <p className={styles.undo}>
            {removal.message}
            <button
              type="button"
              className={styles.undoButton}
              onClick={() => {
                restoreSaved(removal.before);
                setRemoval(null);
              }}
            >
              Undo
            </button>
          </p>
        )}
      </div>

      {hydration !== "pending" && saved.length === 0 && (
        <div className={styles.empty}>
          <p>Recipes you swipe right on land here.</p>
          <Link to={pantry.length > 0 ? "/deck" : "/"} className={styles.primary}>
            Find something to cook
          </Link>
        </div>
      )}

      <ul className={styles.list}>
        {newestFirst.map((id, index) => {
          const query = recipes[index];
          const recipe = query?.data;
          return (
            <li key={id} className={styles.item}>
              <Link to={`/recipe/${id}`} className={styles.row}>
                <DishArt recipeId={id} size={64} />
                <span className={styles.text}>
                  {recipe ? (
                    <>
                      <span className={styles.name}>{recipe.name}</span>
                      <span className={styles.meta}>
                        {recipe.total_minutes} min · {DIETS[recipe.diet]}
                      </span>
                    </>
                  ) : recipe === null ? (
                    <span className={styles.meta}>Unavailable right now</span>
                  ) : query?.isError ? (
                    <span className={styles.meta}>Couldn't load this recipe</span>
                  ) : (
                    <span className={styles.meta}>Loading…</span>
                  )}
                </span>
                <span aria-hidden="true" className={styles.chevron}>
                  ›
                </span>
              </Link>
              <button
                type="button"
                className={styles.remove}
                aria-label={`Remove ${recipe?.name ?? "this recipe"} from your cookbook`}
                onClick={() => {
                  remove(id, recipe?.name);
                }}
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
