import { Link, useParams } from "react-router";

import { RecipeDetail } from "./RecipeDetail";
import styles from "./RecipeScreen.module.css";

/** A saved recipe on its own screen, opened from the cookbook. */
export function RecipeScreen() {
  const { recipeId = "" } = useParams();
  return (
    <main className={styles.screen}>
      <Link to="/saved" className={styles.back}>
        <span aria-hidden="true">←</span> Your cookbook
      </Link>
      <RecipeDetail recipeId={recipeId} />
    </main>
  );
}
