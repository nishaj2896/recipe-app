import { m } from "motion/react";
import type { Ref } from "react";

import { usePrefersReducedMotion } from "../motion/reducedMotion";
import styles from "./VoiceAdd.module.css";

interface Props {
  ref?: Ref<HTMLButtonElement>;
  listening: boolean;
  onStart: () => void;
  onStop: () => void;
}

/** The mic in the search field: "I have potatoes and milk" adds both. */
export function VoiceAdd({ ref, listening, onStart, onStop }: Props) {
  const reduceMotion = usePrefersReducedMotion();

  return (
    <button
      ref={ref}
      type="button"
      className={styles.mic}
      aria-pressed={listening}
      aria-label={listening ? "Stop listening" : "Say what you have"}
      onClick={listening ? onStop : onStart}
    >
      {listening && !reduceMotion && (
        <m.span
          className={styles.ring}
          aria-hidden="true"
          initial={{ scale: 1, opacity: 0.6 }}
          animate={{ scale: 1.8, opacity: 0 }}
          transition={{ duration: 1.1, repeat: Infinity, ease: "easeOut" }}
        />
      )}
      <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
        <rect x="7" y="2" width="6" height="11" rx="3" fill="currentColor" />
        <path
          d="M4 9.5a6 6 0 0 0 12 0M10 15.5V18"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
      </svg>
    </button>
  );
}
