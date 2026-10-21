import { m } from "motion/react";
import { useEffect } from "react";

import type { CatalogIngredient } from "../api/client";
import { IngredientArt, LidArt, PotArt } from "../art/IngredientArt";
import { usePrefersReducedMotion } from "../motion/reducedMotion";
import styles from "./CookingScene.module.css";

/** The scene plays at least this long, so a fast answer never flickers. */
export const SCENE_MS = 1200;

interface Props {
  /** A few of the user's ingredients, dropped into the pot. */
  ingredients: readonly CatalogIngredient[];
  /** False once the deck is ready: then Skip can end the scene. */
  waiting: boolean;
  onDone: () => void;
}

/**
 * The honest loader (ADR-0006 rule 7): the user's own ingredients drop into a
 * bubbling pot while the search runs. It plays on every search for at least
 * 1.2 s and can be skipped; with reduce motion it's a still pot that fades.
 */
export function CookingScene({ ingredients, waiting, onDone }: Props) {
  const reduceMotion = usePrefersReducedMotion();
  const dropped = ingredients.slice(-5);

  useEffect(() => {
    const timer = window.setTimeout(onDone, SCENE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [onDone]);

  return (
    <m.div
      className={styles.scene}
      role="status"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className={styles.stage} aria-hidden="true">
        {!reduceMotion &&
          dropped.map((item, index) => (
            <m.span
              key={item.id}
              className={styles.drop}
              style={{ left: `${String(22 + index * 14)}%` }}
              initial={{ y: -150, rotate: -30, opacity: 0 }}
              animate={{ y: 30, rotate: 160, opacity: [0, 1, 1, 0] }}
              transition={{
                delay: index * 0.14,
                duration: 0.75,
                ease: [0.5, 0, 0.75, 0],
                repeat: Infinity,
                repeatDelay: dropped.length * 0.14,
              }}
            >
              <IngredientArt
                ingredientId={item.id}
                categoryId={item.category.id}
                size={44}
              />
            </m.span>
          ))}
        {!reduceMotion &&
          [0, 1, 2].map((index) => (
            <m.span
              key={index}
              className={styles.steam}
              style={{ left: `${String(36 + index * 13)}%` }}
              animate={{ y: [0, -46], opacity: [0, 0.7, 0], scaleX: [1, 1.6] }}
              transition={{
                duration: 1.4,
                delay: index * 0.35,
                repeat: Infinity,
                ease: "easeOut",
              }}
            />
          ))}
        <m.span
          className={styles.lid}
          animate={
            reduceMotion ? {} : { y: [0, -7, 0, -4, 0], rotate: [0, -3, 2, -1, 0] }
          }
          transition={{ duration: 0.6, repeat: Infinity, repeatDelay: 0.25 }}
        >
          <LidArt size={150} />
        </m.span>
        <span className={styles.pot}>
          <PotArt size={180} />
        </span>
      </div>
      <p className={styles.text}>Cooking up ideas from your pantry…</p>
      {!waiting && (
        <button type="button" className={styles.skip} onClick={onDone}>
          Skip
        </button>
      )}
    </m.div>
  );
}
