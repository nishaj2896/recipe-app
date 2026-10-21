import { useEffect, useState } from "react";

/**
 * False on the first render, true once the browser has painted it.
 *
 * Work that can wait a frame waits for this, so it doesn't land in the same
 * task as a big mount and block a frame (ADR-0006 rule 10).
 */
export function useAfterPaint(): boolean {
  const [painted, setPainted] = useState(false);
  useEffect(() => {
    let timer = 0;
    // A frame callback runs just before the paint; a timeout set there runs
    // just after it.
    const frame = requestAnimationFrame(() => {
      timer = window.setTimeout(() => {
        setPainted(true);
      });
    });
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, []);
  return painted;
}
