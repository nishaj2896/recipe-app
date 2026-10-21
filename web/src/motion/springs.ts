import type { Transition } from "motion/react";

/** Shared springs (ADR-0006 rule 7: springs, not fixed durations). */
export const springs = {
  /** Buttons and tiles answering a press. */
  press: { type: "spring", stiffness: 600, damping: 30 },
  /** The jar's squash-and-stretch when an ingredient lands. */
  bounce: { type: "spring", stiffness: 520, damping: 11 },
} satisfies Record<string, Transition>;
