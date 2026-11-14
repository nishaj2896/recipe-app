import { useEffect, useState } from "react";

/** `value`, once it has stopped changing for `ms`: one search per pause, not per key. */
export function useDebounced<T>(value: T, ms = 200): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => {
      setSettled(value);
    }, ms);
    return () => {
      window.clearTimeout(id);
    };
  }, [value, ms]);
  return settled;
}
