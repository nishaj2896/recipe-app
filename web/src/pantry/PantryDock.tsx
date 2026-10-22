import { AnimatePresence, m, useAnimate } from "motion/react";
import { useEffect } from "react";
import { Link } from "react-router";

import type { CatalogIngredient } from "../api/client";
import { IngredientArt, JarArt } from "../art/IngredientArt";
import { useFlight } from "../motion/flightContext";
import { springs } from "../motion/springs";
import styles from "./PantryDock.module.css";

interface Props {
  items: readonly CatalogIngredient[];
  stapleCount: number;
  onOpenPantry: () => void;
}

/** The jar ingredients fly into, the count, and the way to the deck. */
export function PantryDock({ items, stapleCount, onOpenPantry }: Props) {
  const { jarRef, landings } = useFlight();
  const [scope, animate] = useAnimate<HTMLSpanElement>();

  useEffect(() => {
    if (landings === 0) return;
    void animate(scope.current, { scaleX: [1.14, 1], scaleY: [0.88, 1] }, springs.bounce);
  }, [landings, animate, scope]);

  const count = items.length;
  const recent = items.slice(-4);

  return (
    <div className={styles.dock}>
      <button
        ref={jarRef}
        type="button"
        className={styles.jar}
        aria-label={`Your pantry: ${count} ${count === 1 ? "ingredient" : "ingredients"}`}
        onClick={onOpenPantry}
      >
        <span ref={scope} className={styles.jarBody}>
          <JarArt size={64} />
          <span className={styles.contents}>
            {recent.map((item) => (
              <IngredientArt
                key={item.id}
                ingredientId={item.id}
                categoryId={item.category.id}
                size={22}
              />
            ))}
          </span>
        </span>
      </button>
      <div className={styles.count} aria-live="polite">
        <span className={styles.number}>
          <AnimatePresence initial={false} mode="popLayout">
            <m.span
              key={count}
              initial={{ y: "-100%", opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: "100%", opacity: 0 }}
              transition={springs.press}
            >
              {count}
            </m.span>
          </AnimatePresence>
        </span>
        <span className={styles.label}>
          in pantry
          {stapleCount > 0 && (
            <span className={styles.staples}>+{stapleCount} staples</span>
          )}
        </span>
        {count > 0 && (
          <button
            type="button"
            className={styles.edit}
            aria-label="Edit your pantry"
            onClick={onOpenPantry}
          >
            Edit
          </button>
        )}
      </div>
      {count > 0 ? (
        <Link to="/deck" className={styles.cta}>
          Cook something <span aria-hidden="true">→</span>
        </Link>
      ) : (
        <span className={styles.hint}>Tap what you have</span>
      )}
    </div>
  );
}
