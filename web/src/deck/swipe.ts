export type Direction = "left" | "right";

/** A fling at least this fast commits, however short the drag. */
export const FLING_VELOCITY = 600;
/** A drag past this share of the card's width commits (the motion spec's 35%). */
export const COMMIT_SHARE = 0.35;

/**
 * Whether letting go of a dragged card commits a swipe, and which way.
 * Nothing happens until the finger lifts, and dragging back cancels.
 */
export function swipeOutcome(
  offset: number,
  velocity: number,
  width: number,
): Direction | null {
  const past = Math.abs(offset) >= width * COMMIT_SHARE;
  const flung = Math.abs(velocity) >= FLING_VELOCITY;
  // A fling against the drag is the user changing their mind.
  if (flung && Math.sign(velocity) !== Math.sign(offset) && offset !== 0) return null;
  if (!past && !flung) return null;
  const sign = flung ? Math.sign(velocity) : Math.sign(offset);
  return sign > 0 ? "right" : "left";
}
