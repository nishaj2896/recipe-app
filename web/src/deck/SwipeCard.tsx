import { animate, m, type PanInfo, useMotionValue, useTransform } from "motion/react";
import { type ReactNode, type Ref, useImperativeHandle, useRef, useState } from "react";

import { haptic } from "../motion/haptics";
import { usePrefersReducedMotion } from "../motion/reducedMotion";
import { COMMIT_SHARE, type Direction, swipeOutcome } from "./swipe";
import styles from "./SwipeCard.module.css";

export interface SwipeCardHandle {
  /** Throws the card off the screen, as the Save and Skip buttons do. */
  fling: (direction: Direction) => void;
}

interface Props {
  ref?: Ref<SwipeCardHandle>;
  label: string;
  onSwipe: (direction: Direction) => void;
  children: ReactNode;
}

const RETURN = { type: "spring", stiffness: 500, damping: 32 } as const;

/**
 * The top card of the deck: glued to the finger, with tilt and a SAVE or SKIP
 * stamp that fades in with distance. Nothing happens until the finger lifts;
 * then it either flies off at the finger's speed or springs back (ADR-0006
 * rule 7). Only transform and opacity animate.
 */
export function SwipeCard({ ref, label, onSwipe, children }: Props) {
  const card = useRef<HTMLElement>(null);
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-300, 300], [-16, 16]);
  const saveOpacity = useTransform(x, [24, 120], [0, 1]);
  const skipOpacity = useTransform(x, [-120, -24], [1, 0]);
  const [armed, setArmed] = useState<Direction | null>(null);
  const leaving = useRef(false);
  const reduceMotion = usePrefersReducedMotion();

  function leave(direction: Direction, velocity = 0) {
    if (leaving.current) return;
    leaving.current = true;
    haptic.land();
    // With reduce motion the card doesn't fly; the next one just appears.
    if (reduceMotion) {
      onSwipe(direction);
      return;
    }
    const width = card.current?.offsetWidth ?? 360;
    const distance = (direction === "right" ? 1 : -1) * (window.innerWidth / 2 + width);
    void animate(x, distance, {
      type: "spring",
      stiffness: 260,
      damping: 32,
      velocity,
      restDelta: 20,
    }).then(() => {
      onSwipe(direction);
    });
  }

  useImperativeHandle(ref, () => ({
    fling: (direction) => {
      leave(direction);
    },
  }));

  function onDrag(_event: PointerEvent, info: PanInfo) {
    const width = card.current?.offsetWidth ?? 360;
    const next =
      Math.abs(info.offset.x) >= width * COMMIT_SHARE
        ? info.offset.x > 0
          ? "right"
          : "left"
        : null;
    if (next !== armed) {
      // A tick as the card crosses the line, so the user feels the commit point.
      if (next) haptic.tap();
      setArmed(next);
    }
  }

  function onDragEnd(_event: PointerEvent, info: PanInfo) {
    const width = card.current?.offsetWidth ?? 360;
    const direction = swipeOutcome(info.offset.x, info.velocity.x, width);
    setArmed(null);
    if (direction) leave(direction, info.velocity.x);
    else void animate(x, 0, { ...RETURN, velocity: info.velocity.x });
  }

  return (
    <m.article
      ref={card}
      className={styles.card}
      data-armed={armed ?? undefined}
      aria-label={label}
      drag="x"
      dragMomentum={false}
      onDrag={onDrag}
      onDragEnd={onDragEnd}
      style={{ x, rotate }}
      initial={{ scale: 0.95, y: 14 }}
      animate={{ scale: 1, y: 0 }}
      whileDrag={{ scale: 1.02 }}
      transition={RETURN}
    >
      <m.span
        className={styles.stamp}
        data-kind="save"
        style={{ opacity: saveOpacity }}
        aria-hidden="true"
      >
        Save
      </m.span>
      <m.span
        className={styles.stamp}
        data-kind="skip"
        style={{ opacity: skipOpacity }}
        aria-hidden="true"
      >
        Skip
      </m.span>
      {children}
    </m.article>
  );
}
