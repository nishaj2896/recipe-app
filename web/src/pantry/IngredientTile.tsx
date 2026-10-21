import { m } from "motion/react";
import { useRef } from "react";

import type { CatalogIngredient } from "../api/client";
import { IngredientArt } from "../art/IngredientArt";
import { springs } from "../motion/springs";
import styles from "./IngredientTile.module.css";

interface Props {
  ingredient: CatalogIngredient;
  inPantry: boolean;
  onToggle: (ingredient: CatalogIngredient, art: Element | null) => void;
}

export function IngredientTile({ ingredient, inPantry, onToggle }: Props) {
  const art = useRef<HTMLSpanElement>(null);
  return (
    <m.button
      type="button"
      className={styles.tile}
      aria-pressed={inPantry}
      whileTap={{ scale: 0.92 }}
      transition={springs.press}
      onClick={() => {
        onToggle(ingredient, art.current);
      }}
    >
      <span ref={art} className={styles.art}>
        <IngredientArt ingredientId={ingredient.id} categoryId={ingredient.category.id} />
      </span>
      <span className={styles.name}>{ingredient.name}</span>
      {inPantry && (
        <span className={styles.check} aria-hidden="true">
          ✓
        </span>
      )}
    </m.button>
  );
}
