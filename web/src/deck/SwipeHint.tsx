import { m } from "motion/react";

import { usePrefersReducedMotion } from "../motion/reducedMotion";
import styles from "./SwipeHint.module.css";

/**
 * The first-run hint: a ghost finger drags right across the top card, over
 * and over, until the user's first swipe. It rides on the card, so it leaves
 * with it, and it never takes a touch. With reduce motion the finger rests at
 * the end of its arrow instead.
 */
export function SwipeHint() {
  const reduceMotion = usePrefersReducedMotion();

  return (
    <div className={styles.hint}>
      <div className={styles.track} aria-hidden="true">
        <m.span
          className={styles.trail}
          initial={{ scaleX: reduceMotion ? 1 : 0 }}
          animate={reduceMotion ? {} : { scaleX: [0, 1, 1], opacity: [1, 1, 0] }}
          transition={{
            duration: 1.6,
            times: [0, 0.6, 1],
            repeat: Infinity,
            repeatDelay: 0.5,
            ease: "easeInOut",
          }}
        />
        <span className={styles.arrow}>›</span>
        <m.span
          className={styles.finger}
          initial={{ x: reduceMotion ? 150 : 0 }}
          animate={
            reduceMotion
              ? {}
              : { x: [0, 150, 150], opacity: [0, 1, 0], scale: [0.9, 1, 0.9] }
          }
          transition={{
            duration: 1.6,
            times: [0, 0.6, 1],
            repeat: Infinity,
            repeatDelay: 0.5,
            ease: "easeInOut",
          }}
        />
      </div>
      <p className={styles.text}>Swipe right to save, left to skip</p>
    </div>
  );
}
