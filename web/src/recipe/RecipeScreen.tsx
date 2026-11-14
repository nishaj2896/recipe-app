import { useEffect } from "react";
import { Link, useParams } from "react-router";

import { RecipeDetail } from "./RecipeDetail";
import styles from "./RecipeScreen.module.css";

/** A saved recipe on its own screen, opened from the cookbook. */
export function RecipeScreen() {
  const { recipeId = "" } = useParams();
  // A "Pairs well with" link opens another recipe on this same screen: start
  // it at the top, not at the scroll position of the last one.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [recipeId]);
  return (
    <main className={styles.screen}>
      <Link to="/saved" className={styles.back}>
        <span aria-hidden="true">←</span> Your cookbook
      </Link>
      <RecipeDetail recipeId={recipeId} />
    </main>
  );
}
