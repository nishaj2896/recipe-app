import { m } from "motion/react";

import type { CatalogIngredient } from "../api/client";
import { IngredientArt } from "../art/IngredientArt";
import { springs } from "../motion/springs";
import type { QuickStart } from "./presets";
import styles from "./QuickStarts.module.css";

interface Props {
  presets: readonly { preset: QuickStart; items: readonly CatalogIngredient[] }[];
  onPick: (items: readonly CatalogIngredient[], origin: Element) => void;
}

/** One tap fills the pantry with a typical kitchen. */
export function QuickStarts({ presets, onPick }: Props) {
  return (
    <section aria-labelledby="quick-start">
      <h2 id="quick-start" className={styles.heading}>
        Quick start
      </h2>
      <div className={styles.row}>
        {presets.map(({ preset, items }) => (
          <m.button
            key={preset.id}
            type="button"
            className={styles.chip}
            whileTap={{ scale: 0.95 }}
            transition={springs.press}
            onClick={(event) => {
              onPick(items, event.currentTarget);
            }}
          >
            <span className={styles.art} aria-hidden="true">
              {items.slice(0, 2).map((item) => (
                <IngredientArt
                  key={item.id}
                  ingredientId={item.id}
                  categoryId={item.category.id}
                  size={30}
                />
              ))}
            </span>
            <span className={styles.text}>
              <span className={styles.name}>{preset.name}</span>
              <span className={styles.count}>{items.length} items</span>
            </span>
          </m.button>
        ))}
      </div>
    </section>
  );
}
