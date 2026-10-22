import { useQueries } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";

import { recipeQuery } from "../api/queries";
import { DishArt } from "../art/IngredientArt";
import { DIETS } from "../deck/diets";
import { InstallNudge } from "../install/InstallNudge";
import { type SavedPlace, useDevice } from "../store/device";
import styles from "./CookbookScreen.module.css";

/** Every recipe the user saved, newest first. */
export function CookbookScreen() {
  const saved = useDevice((state) => state.saved);
  const pantry = useDevice((state) => state.pantry);
  const hydration = useDevice((state) => state.hydration);
  const { unsaveRecipe, clearSaved, restoreSaved } = useDevice.getState();
  const newestFirst = [...saved].reverse();
  const recipes = useQueries({ queries: newestFirst.map((id) => recipeQuery(id)) });
  // The last removal, so it can be undone: what it said, and where each
  // recipe was. Undo puts back only those, so saves made since are kept.
  const [removal, setRemoval] = useState<{
    message: string;
    /** Said once Undo has put the recipes back. */
    undone: string;
    removed: SavedPlace[];
  } | null>(null);
  // What the status line says after an Undo.
  const [notice, setNotice] = useState("");
  // The row to focus once an Undo has put it back.
  const [focusRow, setFocusRow] = useState<string | null>(null);
  const undoButton = useRef<HTMLButtonElement>(null);
  const rows = useRef(new Map<string, HTMLAnchorElement>());

  // A removed row takes its focused button with it, so focus moves to Undo.
  useEffect(() => {
    if (removal) undoButton.current?.focus();
  }, [removal]);

  useEffect(() => {
    if (focusRow === null) return;
    const row = rows.current.get(focusRow);
    if (!row) return;
    row.focus();
    setFocusRow(null);
  }, [focusRow, saved]);

  function remove(id: string, name: string | undefined) {
    setNotice("");
    setRemoval({
      message: `Removed ${name ?? "a recipe"}.`,
      undone: `Put ${name ?? "the recipe"} back in your cookbook.`,
      removed: [{ id, index: saved.indexOf(id) }],
    });
    unsaveRecipe(id);
  }

  function removeAll() {
    const count = saved.length;
    setNotice("");
    setRemoval({
      message: `Removed ${String(count)} ${count === 1 ? "recipe" : "recipes"}.`,
      undone: `Put ${String(count)} ${count === 1 ? "recipe" : "recipes"} back in your cookbook.`,
      removed: saved.map((id, index) => ({ id, index })),
    });
    clearSaved();
  }

  function undo(current: { undone: string; removed: SavedPlace[] }) {
    restoreSaved(current.removed);
    setRemoval(null);
    setNotice(current.undone);
    // The newest of them, which is the highest on the page.
    const newest = current.removed.reduce((a, b) => (b.index > a.index ? b : a));
    setFocusRow(newest.id);
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
        {removal ? (
          <p className={styles.undo}>
            {removal.message}
            <button
              ref={undoButton}
              type="button"
              className={styles.undoButton}
              onClick={() => {
                undo(removal);
              }}
            >
              Undo
            </button>
          </p>
        ) : (
          notice && <p className={styles.notice}>{notice}</p>
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
              <Link
                ref={(element) => {
                  if (element) rows.current.set(id, element);
                  else rows.current.delete(id);
                }}
                to={`/recipe/${id}`}
                className={styles.row}
              >
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
