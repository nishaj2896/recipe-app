/**
 * Haptics on every committed tap or swipe (ADR-0006 rule 7). The Vibration
 * API exists on Android only; elsewhere these do nothing.
 */
function vibrate(pattern: number | number[]): void {
  if (typeof navigator.vibrate === "function") navigator.vibrate(pattern);
}

export const haptic = {
  /** A light tick the moment a tap registers. */
  tap: () => {
    vibrate(8);
  },
  /** A softer second beat when something lands where it lives. */
  land: () => {
    vibrate(12);
  },
};
